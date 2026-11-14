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

/** Artifact choices shown when adding a missing output to one lecture or the whole course. */
const ARTIFACT_TYPE_CHOICES = {
  chapter: [
    { value: 'audio', label: '語音摘要' },
    { value: 'quiz_1', label: '測驗 1・基礎' },
    { value: 'quiz_2', label: '測驗 2・理解' },
    { value: 'quiz_3', label: '測驗 3・模擬考' },
    { value: 'quiz_academic', label: '測驗・學術精研' },
    { value: 'quiz_concept', label: '測驗・概念刷題' },
    { value: 'flashcards', label: '閃卡' },
    { value: 'mind_map', label: '心智圖' },
    { value: 'infographic', label: '資訊圖表' },
    { value: 'study_guide', label: '讀書指南' },
    { value: 'slide_deck', label: '投影片' },
    { value: 'data_table', label: '資料表' },
    { value: 'video', label: '影片摘要' },
    { value: 'reports_briefing', label: '報告・簡報文件' },
    { value: 'reports_study_guide', label: '報告・讀書指南' },
    { value: 'reports_blog_post', label: '報告・部落格文章' },
    { value: 'reports_concept_explanation', label: '報告・概念解說' },
  ],
  course: [
    { value: 'course_mock_exam', label: '全課程期末模擬考' },
    { value: 'course_quiz_academic', label: '全課程・學術精研考' },
    { value: 'course_quiz_concept', label: '全課程・概念刷題考' },
    { value: 'course_mind_map', label: '全課程心智圖' },
    { value: 'course_audio', label: '全課程語音摘要' },
    { value: 'course_study_guide', label: '全課程讀書指南' },
    { value: 'course_infographic', label: '全課程資訊圖表' },
    { value: 'course_slide_deck', label: '全課程投影片' },
    { value: 'course_data_table', label: '全課程資料表' },
    { value: 'course_video', label: '全課程影片' },
    { value: 'course_reports_briefing', label: '全課程報告・簡報文件' },
    { value: 'course_reports_study_guide', label: '全課程報告・讀書指南' },
    { value: 'course_reports_blog_post', label: '全課程報告・部落格文章' },
    { value: 'course_reports_concept_explanation', label: '全課程報告・概念解說' },
  ],
};

/**
 * Render an inline picker to add any unqueued artifact type for one lecture or the whole course.
 * @param {string} code Course code
 * @param {string|number} key Group key ('course' or lecture number)
 * @param {Array<object>} list Active (non-skipped) jobs currently in this group
 * @returns {string} HTML snippet or empty string when all types are present
 */
function addArtifactBarHtml(code, key, list) {
  const choices = key === 'course' ? ARTIFACT_TYPE_CHOICES.course : ARTIFACT_TYPE_CHOICES.chapter;
  const existing = new Set(list.map(j => j.artifact_type));
  const missing = choices.filter(c => !existing.has(c.value));
  if (!missing.length) return '';
  const opts = missing.map(c => `<option value="${c.value}">${escHtml(c.label)}</option>`).join('');
  const lecArg = key === 'course' ? 'null' : key;
  return `<div class="row" style="margin-top:10px;gap:8px;flex-wrap:wrap;align-items:center">
    <select class="select" id="addArt_${escHtml(code)}_${key}" aria-label="選擇要補生成的產出">${opts}</select>
    <button type="button" class="btn btn-soft btn-sm" onclick="addSingleArtifact('${escHtml(code)}', ${lecArg})">＋ 新增並生成</button>
  </div>`;
}

/**
 * Queue and start a missing artifact type for a single lecture or the whole course.
 * @param {string} code Course code
 * @param {number|null} lectureNo Lecture number, or null for whole course
 * @returns {Promise<void>} Resolves after queuing
 */
async function addSingleArtifact(code, lectureNo) {
  const key = lectureNo === null ? 'course' : lectureNo;
  const select = document.getElementById(`addArt_${code}_${key}`);
  if (!select || !select.value) return;
  const artifactType = select.value;
  const label = (select.options[select.selectedIndex] || {}).textContent || artifactType;
  const scope = lectureNo === null ? '全課程' : `第 ${pad2(lectureNo)} 講`;
  try {
    const res = await fetch(`/api/courses/${code}/jobs/regenerate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ artifact_type: artifactType, lecture_no: lectureNo }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已將 ${scope}「${data.label || label}」排入佇列並啟動生成`, 'success');
    await fetchStatus();
    await fetchCourses();
    await viewCourseDetail(code, true);
  } catch (e) {
    showToast('新增產出失敗：' + e.message, 'error');
  }
}
