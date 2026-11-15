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

/**
 * Escape text safely for HTML attribute values.
 * @param {*} value Text to escape
 * @returns {string} Escaped attribute string
 */
function escAttr(value) {
  return escHtml(value).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/**
 * Render a status badge for a remote source or local lecture upload state.
 * @param {string} status Status string
 * @returns {string} HTML badge span
 */
function sourceStatusBadge(status) {
  const st = String(status || 'pending').toLowerCase();
  const cls = st === 'ready' ? 'badge-success' : ['uploading', 'parsing', 'processing'].includes(st) ? 'badge-warning' : ['failed', 'error'].includes(st) ? 'badge-danger' : '';
  return `<span class="badge ${cls}">${escHtml(st)}</span>`;
}

/**
 * Render the top action toolbar for Gemini Notebook source management.
 * @param {object} data Response from GET /api/courses/{code}/sources
 * @param {string} code Course code
 * @returns {string} HTML toolbar string
 */
function sourceToolbarHtml(data, code) {
  const link = data.notebook_url
    ? `<a href="${escAttr(data.notebook_url)}" target="_blank" rel="noopener" class="btn btn-ghost btn-sm">開啟 Gemini Notebook ↗</a>`
    : '<span class="badge badge-warning">尚未建立遠端筆記本</span>';
  return `<div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center">
    ${link}
    <button type="button" class="btn btn-ghost btn-sm" onclick="loadCourseSources('${escAttr(code)}')">重新整理來源</button>
    <button type="button" class="btn btn-soft btn-sm" onclick="setupCourse('${escAttr(code)}', event)">補傳未上傳講義</button>
    <label class="btn btn-primary btn-sm" style="cursor:pointer">＋ 上傳 PDF 到筆記本<input type="file" accept=".pdf,application/pdf" hidden onchange="uploadCustomSourcePdf('${escAttr(code)}', this)"></label>
    <button type="button" class="btn btn-soft btn-sm" onclick="addUrlSourceUi('${escAttr(code)}')">網址 / YouTube</button>
    <button type="button" class="btn btn-soft btn-sm" onclick="addTextSourceUi('${escAttr(code)}')">貼上文字</button>
    <button type="button" class="btn btn-soft btn-sm" onclick="researchSourcesUi('${escAttr(code)}')">網路研究搜來源</button>
    <button type="button" class="btn btn-primary btn-sm" onclick="generateFromSelectedSourcesUi('${escAttr(code)}')">依勾選來源生成</button>
  </div>`;
}

/**
 * Render one row in the remote Gemini Notebook sources table.
 * @param {object} src Source metadata from GET /api/courses/{code}/sources
 * @param {string} code Course code
 * @returns {string} HTML table row
 */
function remoteSourceRowHtml(src, code) {
  const title = src.title || src.id;
  const words = src.word_count ? `<div class="job-sub">${Number(src.word_count).toLocaleString()} 字</div>` : '';
  const matched = src.lecture_no ? `第 ${pad2(src.lecture_no)} 講・${escHtml(src.lecture_topic || '')}` : '額外來源';
  return `<tr><td><input type="checkbox" class="src-pick" value="${escAttr(src.id)}" aria-label="選取來源 ${escAttr(title)}"></td>
    <td><code>${escHtml(title)}</code>${words}</td><td>${sourceStatusBadge(src.status)}</td><td>${matched}</td><td><code>${escHtml(src.id)}</code></td>
    <td><button type="button" class="btn btn-ghost btn-sm" style="color:var(--danger)" data-code="${escAttr(code)}" data-source-id="${escAttr(src.id)}" data-title="${escAttr(title)}" onclick="deleteNotebookSource(this.dataset.code, this.dataset.sourceId, this.dataset.title)">刪除</button></td></tr>`;
}

/**
 * Render the remote Gemini Notebook sources section.
 * @param {object} data Response from GET /api/courses/{code}/sources
 * @param {string} code Course code
 * @returns {string} HTML snippet
 */
function remoteSourcesTableHtml(data, code) {
  if (data.remote_error) return `<p class="small" style="color:var(--danger)">無法讀取遠端筆記本來源：${escHtml(data.remote_error)}</p>`;
  if (!data.notebook_id) return '<p class="small muted">尚未建立 Gemini Notebook 筆記本；上傳任一 PDF 或按「補傳未上傳講義」後會自動建立。</p>';
  const rows = data.sources || [];
  if (!rows.length) return '<p class="small muted">遠端筆記本目前沒有來源檔案。</p>';
  return `<table><thead><tr><th>選</th><th>來源名稱</th><th>狀態</th><th>對應講次</th><th>來源 ID</th><th></th></tr></thead><tbody>
    ${rows.map(s => remoteSourceRowHtml(s, code)).join('')}</tbody></table>`;
}

/**
 * Render the local course lectures upload and unlink management table.
 * @param {object} data Response from GET /api/courses/{code}/sources
 * @param {string} code Course code
 * @returns {string} HTML snippet
 */
function courseLecturesSourcesHtml(data, code) {
  const rows = data.lectures || [];
  if (!rows.length) return '<p class="small muted">尚未掃描到課程講義 PDF。</p>';
  const body = rows.map(l => {
    const upLabel = l.source_id ? '重傳' : '上傳';
    const rmBtn = l.source_id
      ? `<button type="button" class="btn btn-ghost btn-sm" style="color:var(--danger)" data-code="${escAttr(code)}" data-source-id="${escAttr(l.source_id)}" data-title="${escAttr(l.filename)}" onclick="deleteNotebookSource(this.dataset.code, this.dataset.sourceId, this.dataset.title)">移除遠端</button>` : '';
    return `<tr><td>L${pad2(l.no)}</td><td>${escHtml(l.topic)}</td><td><code>${escHtml(l.filename)}</code></td><td>${sourceStatusBadge(l.upload_status)}</td><td><code>${escHtml(l.source_id || '—')}</code></td>
      <td><div style="display:flex;gap:6px;flex-wrap:wrap"><button type="button" class="btn btn-soft btn-sm" onclick="uploadLectureSource('${escAttr(code)}', ${l.no})">${upLabel}</button>${rmBtn}</div></td></tr>`;
  }).join('');
  return `<table><thead><tr><th>講次</th><th>主題</th><th>檔名</th><th>狀態</th><th>來源 ID</th><th></th></tr></thead><tbody>${body}</tbody></table>`;
}

/**
 * Fetch and render Gemini Notebook sources and local lecture upload statuses for a course.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when rendered
 */
async function loadCourseSources(code) {
  const box = document.getElementById('detailSources');
  const sum = document.getElementById('detailSourcesSummary');
  if (!box) return;
  try {
    const res = await fetch(`/api/courses/${code}/sources`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const remoteN = (data.sources || []).length;
    const lecN = (data.lectures || []).length;
    if (sum) sum.textContent = `遠端 ${remoteN} 份來源 · 課程講義 ${lecN} 份`;
    box.innerHTML = sourceToolbarHtml(data, code) +
      '<h4 class="small muted" style="margin:6px 0">遠端筆記本來源</h4>' + remoteSourcesTableHtml(data, code) +
      '<h4 class="small muted" style="margin:14px 0 6px">課程資料夾講義</h4>' + courseLecturesSourcesHtml(data, code);
  } catch (e) {
    box.innerHTML = `<p style="color:var(--danger)">來源載入失敗：${escHtml(e.message)}</p>`;
  }
}

/**
 * Upload or re-upload one lecture PDF to the course's Gemini Notebook.
 * @param {string} code Course code
 * @param {number} lectureNo Lecture sequence number
 * @returns {Promise<void>} Resolves when upload completes
 */
async function uploadLectureSource(code, lectureNo) {
  try {
    showToast(`正在上傳第 ${pad2(lectureNo)} 講到 Gemini Notebook…`, 'info', 8000);
    const res = await fetch(`/api/courses/${code}/sources`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lecture_no: lectureNo }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`第 ${pad2(lectureNo)} 講已上傳（${data.source_id || 'ready'}）`, 'success');
    await loadCourseSources(code);
    await fetchCourses();
    await viewCourseDetail(code, true);
  } catch (e) {
    showToast('上傳講義失敗：' + e.message, 'error');
  }
}

/**
 * Read a browser File object into a pure Base64 string.
 * @param {File} file Selected file
 * @returns {Promise<string>} Base64 string without data URL prefix
 */
function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || '').split(',').pop() || '');
    reader.onerror = () => reject(reader.error || new Error('無法讀取檔案'));
    reader.readAsDataURL(file);
  });
}

/**
 * Upload a user-picked PDF file from the browser to the course's Gemini Notebook.
 * @param {string} code Course code
 * @param {HTMLInputElement} inputEl File input element
 * @returns {Promise<void>} Resolves when upload finishes
 */
async function uploadCustomSourcePdf(code, inputEl) {
  const file = inputEl && inputEl.files && inputEl.files[0];
  if (!file) return;
  try {
    if (!file.name.toLowerCase().endsWith('.pdf')) throw new Error('只支援上傳 .pdf 檔案');
    showToast(`正在上傳「${file.name}」到 Gemini Notebook…`, 'info', 10000);
    const contentBase64 = await readFileAsBase64(file);
    const res = await fetch(`/api/courses/${code}/sources`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name, content_base64: contentBase64 }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已上傳「${data.filename || file.name}」到筆記本`, 'success');
    await loadCourseSources(code);
    await fetchCourses();
    await viewCourseDetail(code, true);
  } catch (e) {
    showToast('上傳 PDF 失敗：' + e.message, 'error');
  } finally {
    inputEl.value = '';
  }
}

/**
 * Delete a source from Gemini Notebook after user confirmation.
 * @param {string} code Course code
 * @param {string} sourceId Remote source identifier
 * @param {string} title Display title shown in confirmation prompt
 * @returns {Promise<void>} Resolves when deletion finishes
 */
async function deleteNotebookSource(code, sourceId, title) {
  const msg = `確定從 Gemini Notebook 刪除來源「${title}」？\n\n• 遠端筆記本會移除這份來源\n• 本機課程資料夾中的 PDF 不會被刪除`;
  if (!(await askConfirm(msg, { okLabel: '刪除來源', danger: true }))) return;
  try {
    const res = await fetch(`/api/courses/${code}/sources/${encodeURIComponent(sourceId)}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已從筆記本刪除「${title}」`, 'success');
    await loadCourseSources(code);
    await fetchCourses();
    await viewCourseDetail(code, true);
  } catch (e) {
    showToast('刪除來源失敗：' + e.message, 'error');
  }
}
