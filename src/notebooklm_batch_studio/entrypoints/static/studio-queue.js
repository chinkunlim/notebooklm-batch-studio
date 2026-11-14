/**
 * Gemini Notebook 學習工作室 — queue controls, remote sync, and prompt refinement actions.
 * Loaded immediately after studio-batch.js (relies on activeCourseCode, currentStudyCourse,
 * fetchStatus, fetchCourses, viewCourseDetail, loadStudyCourseData, showToast).
 */

/**
 * Show only the queue buttons that fit the current execution state.
 * @param {boolean} start Show 啟動批次生成 button
 * @param {boolean} pause Show 溫和暫停 button
 * @param {boolean} resume Show 繼續執行 button
 */
function setQueueButtonsVisible(start, pause, resume) {
  document.getElementById('btnStartQueue').style.display = start ? '' : 'none';
  document.getElementById('btnPauseQueue').style.display = pause ? '' : 'none';
  document.getElementById('btnResumeQueue').style.display = resume ? '' : 'none';
}

/**
 * Retry a single failed or needs_review job immediately and wake the queue.
 * @param {string} jobId Task UUID
 * @param {string} [code] Optional active course code to refresh detail view
 * @returns {Promise<void>} Resolves after retry request
 */
async function retryJob(jobId, code) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/retry`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '重試失敗');
    showToast('已重新排入佇列並啟動重試。', 'success', 2500);
    await fetchStatus();
    await fetchCourses();
    if (code) await viewCourseDetail(code, true);
  } catch (e) {
    showToast('重試失敗：' + e.message, 'error');
  }
}

/**
 * Re-queue every failed or needs_review job in a course and start the worker pool.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves after re-queue request
 */
async function retryFailedJobs(code) {
  try {
    const res = await fetch(`/api/courses/${code}/jobs/retry-failed`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '重試失敗');
    const n = data.retried_count ?? 0;
    showToast(n > 0 ? `已重新排入 ${n} 項失敗／需審查工作，佇列已啟動。` : '目前沒有失敗或需審查的工作。', n > 0 ? 'success' : 'info');
    await fetchStatus();
    await fetchCourses();
    await viewCourseDetail(code, true);
  } catch (e) {
    showToast('批次重試失敗：' + e.message, 'error');
  }
}

/** Start the generation queue. */
async function startQueue() {
  try {
    await fetch('/api/queue/start', { method: 'POST' });
    await fetchStatus();
    await fetchCourses();
  } catch (e) {
    showToast('啟動佇列失敗：' + e.message, 'error');
  }
}

/** Pause the queue after the running job finishes. */
async function pauseQueue() {
  try {
    await fetch('/api/queue/pause', { method: 'POST' });
    await fetchStatus();
    await fetchCourses();
  } catch (e) {
    showToast('暫停佇列失敗：' + e.message, 'error');
  }
}

/** Resume the paused queue. */
async function resumeQueue() {
  try {
    await fetch('/api/queue/resume', { method: 'POST' });
    await fetchStatus();
    await fetchCourses();
  } catch (e) {
    showToast('繼續執行失敗：' + e.message, 'error');
  }
}

/**
 * Create the course's notebook on Gemini Notebook and upload its PDFs.
 * @param {string} code Course code
 * @param {Event} [event] Click event (kept from bubbling to the row)
 * @returns {Promise<void>} Resolves when setup completes
 */
async function setupCourse(code, event) {
  if (event) event.stopPropagation();
  try {
    showToast(`正在為 ${code} 建立筆記本並上傳講義 PDF，約需 1–2 分鐘…`, 'info', 8000);
    const res = await fetch(`/api/courses/${code}/setup`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '建立筆記本失敗');
    }
    const data = await res.json();
    showToast(`筆記本建立成功（${data.notebook_id}）`, 'success');
    fetchCourses();
    if (activeCourseCode === code) viewCourseDetail(code);
  } catch (e) {
    showToast('建立筆記本失敗：' + e.message, 'error');
  }
}

/**
 * Upload one lecture PDF again after a failed upload.
 * @param {string} code Course code
 * @param {number} lectureNo Lecture number
 * @returns {Promise<void>} Resolves after retry request
 */
async function retryUpload(code, lectureNo) {
  try {
    showToast(`重新上傳第 ${lectureNo} 講…`, 'info');
    const res = await fetch(`/api/courses/${code}/lectures/${lectureNo}/retry_upload`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '重試上傳失敗');
    }
    const data = await res.json();
    showToast(`講義上傳狀態：${data.upload_status}`, 'info');
    await fetchCourses();
    await viewCourseDetail(code, true);
  } catch (e) {
    showToast('重試上傳失敗：' + e.message, 'error');
  }
}

/**
 * Polish every job prompt of a course with the local model.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves after refinement
 */
async function refinePrompts(code) {
  try {
    showToast(`正在用本機模型潤飾 ${code} 的所有 Prompt…`, 'info', 8000);
    const res = await fetch(`/api/courses/${code}/refine_prompts`, { method: 'POST' });
    if (!res.ok) throw new Error('潤飾失敗');
    const data = await res.json();
    showToast(`已潤飾 ${data.updated_jobs_count} 項 Prompt`, 'success');
    viewCourseDetail(code);
  } catch (e) {
    showToast('Prompt 潤飾失敗：' + e.message, 'error');
  }
}

/**
 * Download outputs that were made on the Gemini Notebook website.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves after remote sync
 */
async function syncFromNotebookLM(code) {
  try {
    showToast(`正在查詢 ${code} 在 Gemini Notebook 上的產出並下載…`, 'info', 8000);
    const res = await fetch(`/api/courses/${code}/sync`, { method: 'POST' });
    if (!res.ok) throw new Error('同步失敗');
    const data = await res.json();
    showToast(`同步完成：遠端共 ${data.remote_artifacts_found} 項，下載了 ${data.synced_count} 個新檔案`, 'success');
    await fetchCourses();
    await viewCourseDetail(code, true);
    if (currentStudyCourse && currentStudyCourse.code === code && typeof loadStudyCourseData === 'function') {
      await loadStudyCourseData(code, true);
    }
  } catch (e) {
    showToast('同步失敗：' + e.message, 'error');
  }
}

/**
 * Wake the jobs waiting for quota and resume the queue.
 * @returns {Promise<void>} Resolves after resuming
 */
async function resumeQuota() {
  try {
    const res = await fetch('/api/queue/resume', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast(`已喚醒 ${data.data} 個等待額度的工作，佇列繼續執行。`, 'success');
    await fetchStatus();
  } catch (e) {
    showToast('喚醒失敗：' + e.message, 'error');
  }
}
