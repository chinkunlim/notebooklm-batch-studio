/**
 * Phase 1 & 2 modular Markdown note generation UI controller (Refs: ADR-012).
 */

let _ngPromptsCache = [];
let _ngCoursesCache = [];
let _ngActiveCourseDetail = null;

/**
 * Load standalone modular prompt template metadata and registered courses.
 * @returns {Promise<void>}
 */
async function initNoteGenPanel() {
  try {
    const res = await fetch('/api/notes/prompts');
    const data = await res.json();
    _ngPromptsCache = data.prompts || [];
    const sel = document.getElementById('ngPromptStep');
    if (sel && _ngPromptsCache.length) {
      sel.innerHTML = _ngPromptsCache
        .map((p) => `<option value="${escHtml(p.step_id)}">${escHtml(p.step_id)} — ${escHtml(p.title)}</option>`)
        .join('');
      await previewNotePrompt();
    }
  } catch (err) {
    console.error('Failed to load note prompt specs:', err);
  }
  await loadNoteGenCourses();
}

/**
 * Fetch registered courses into `#ngCourseSelect` for one-click auto-fill.
 * @returns {Promise<void>}
 */
async function loadNoteGenCourses() {
  const sel = document.getElementById('ngCourseSelect');
  if (!sel) return;
  try {
    const res = await fetch('/api/courses');
    const data = await res.json();
    _ngCoursesCache = data.courses || data || [];
    const opts = ['<option value="">（手動填寫或暫存 scratch）</option>'].concat(
      _ngCoursesCache.map((c) => `<option value="${escHtml(c.code)}">${escHtml(c.code)} — ${escHtml(c.name)}</option>`),
    );
    sel.innerHTML = opts.join('');
  } catch (err) {
    console.error('Failed to load courses for note generation:', err);
  }
}

/**
 * Auto-fill course fields and populate lecture selector when a course is chosen.
 * @returns {Promise<void>}
 */
async function onNoteGenCourseSelect() {
  const code = document.getElementById('ngCourseSelect')?.value || '';
  const lecSel = document.getElementById('ngLectureSelect');
  if (!code) {
    _ngActiveCourseDetail = null;
    if (lecSel) lecSel.innerHTML = '<option value="">（手動填寫章節）</option>';
    return;
  }
  try {
    const res = await fetch(`/api/courses/${encodeURIComponent(code)}`);
    const detail = await res.json();
    _ngActiveCourseDetail = detail;
    const keyEl = document.getElementById('ngCourseKey');
    const nameEl = document.getElementById('ngCourseName');
    const nbEl = document.getElementById('ngNotebookId');
    if (keyEl) keyEl.value = detail.code || code;
    if (nameEl) nameEl.value = detail.name || code;
    if (nbEl) nbEl.value = detail.notebook_id || '';
    const lectures = detail.lectures || [];
    if (lecSel) {
      lecSel.innerHTML = ['<option value="">（手動填寫章節）</option>']
        .concat(
          lectures.map(
            (l) => `<option value="${escHtml(l.no)}">${String(l.no).padStart(2, '0')} — ${escHtml(l.topic || l.filename)}</option>`,
          ),
        )
        .join('');
    }
    await previewNotePrompt();
    await loadGeneratedChaptersList();
  } catch (err) {
    console.error('Failed to load course detail:', err);
  }
}

/**
 * Auto-fill chapter ID, title, PDF path, and source_id when a lecture is chosen.
 * @returns {Promise<void>}
 */
async function onNoteGenLectureSelect() {
  const lecNo = Number(document.getElementById('ngLectureSelect')?.value || 0);
  if (!lecNo || !_ngActiveCourseDetail) return;
  // Course detail lectures use `no` (not `lecture_no`). Refs: ISSUE-056
  const lec = (_ngActiveCourseDetail.lectures || []).find((l) => l.no === lecNo);
  if (!lec) return;
  const chId = `ch${String(lec.no).padStart(2, '0')}`;
  const stem = String(lec.filename || '').replace(/\.pdf$/i, '');
  const chEl = document.getElementById('ngChapterId');
  const titleEl = document.getElementById('ngChapterTitle');
  const pdfEl = document.getElementById('ngPdfPath');
  const srcEl = document.getElementById('ngSourceIds');
  if (chEl) chEl.value = chId;
  if (titleEl) titleEl.value = lec.topic || stem;
  if (pdfEl && _ngActiveCourseDetail.source_dir) {
    const rel = lec.relative_path || lec.filename;
    pdfEl.value = `${_ngActiveCourseDetail.source_dir}/${rel}`;
  }
  if (srcEl) srcEl.value = lec.source_id || '';
  await previewNotePrompt();
  await loadStitchedNoteContent();
}

/**
 * Render the selected `.md` prompt template with the current course and chapter fields.
 * @returns {Promise<void>}
 */
async function previewNotePrompt() {
  const stepId = document.getElementById('ngPromptStep')?.value || '01_mindmap';
  const courseName = document.getElementById('ngCourseName')?.value.trim() || '測試課程';
  const chapterId = document.getElementById('ngChapterId')?.value.trim() || 'ch01';
  const chapterTitle = document.getElementById('ngChapterTitle')?.value.trim() || '';
  const meta = _ngPromptsCache.find((p) => p.step_id === stepId);
  const pathEl = document.getElementById('ngPromptPath');
  if (pathEl && meta) pathEl.textContent = `範本檔案：${meta.path}`;
  try {
    const res = await fetch('/api/notes/prompts/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        step_id: stepId,
        course_name: courseName,
        chapter_id: chapterId,
        chapter_title: chapterTitle,
      }),
    });
    const data = await res.json();
    const box = document.getElementById('ngPromptPreview');
    if (box) box.value = data.prompt || data.detail || '';
  } catch (err) {
    console.error('Failed to preview prompt:', err);
  }
}

/**
 * Copy the rendered prompt text to the clipboard for manual browser testing.
 * @returns {Promise<void>}
 */
async function copyNotePrompt() {
  const box = document.getElementById('ngPromptPreview');
  if (!box || !box.value) return;
  await navigator.clipboard.writeText(box.value);
  const banner = document.getElementById('ngStatusBanner');
  if (banner) banner.textContent = '已複製完整提示詞到剪貼簿，可直接貼入 Gemini 手動測試。';
}

/**
 * Trigger Phase 1 modular note generation and stitching for the specified chapter.
 * @returns {Promise<void>}
 */
async function startNoteChapterGeneration() {
  const courseKey = document.getElementById('ngCourseKey')?.value.trim();
  const courseName = document.getElementById('ngCourseName')?.value.trim() || courseKey;
  const chapterId = document.getElementById('ngChapterId')?.value.trim() || 'ch01';
  if (!courseKey) {
    alert('請先填寫課程代碼。');
    return;
  }
  const srcRaw = document.getElementById('ngSourceIds')?.value.trim() || '';
  const payload = {
    course_key: courseKey,
    course_name: courseName,
    chapter_id: chapterId,
    chapter_title: document.getElementById('ngChapterTitle')?.value.trim() || '',
    pdf_path: document.getElementById('ngPdfPath')?.value.trim() || '',
    backend: document.getElementById('ngBackend')?.value || 'gemini_web',
    model: document.getElementById('ngModel')?.value.trim() || '4 Argon',
    notebook_id: document.getElementById('ngNotebookId')?.value.trim() || '',
    source_ids: srcRaw ? srcRaw.split(',').map((s) => s.trim()).filter(Boolean) : [],
  };
  const banner = document.getElementById('ngStatusBanner');
  if (banner) banner.textContent = `正在以 ${payload.backend} 生成 ${chapterId}...`;
  try {
    const res = await fetch('/api/notes/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '生成失敗');
    if (banner) banner.textContent = `狀態：${data.status}（${data.stitched_path || ''}）`;
    await loadGeneratedChaptersList();
    await loadStitchedNoteContent();
  } catch (err) {
    if (banner) banner.textContent = `錯誤：${err.message}`;
  }
}

/**
 * Request a clean pause for the active course note generation pipeline.
 * @returns {Promise<void>}
 */
async function pauseNoteGeneration() {
  const courseKey = document.getElementById('ngCourseKey')?.value.trim();
  if (!courseKey) return;
  await fetch(`/api/notes/pause/${encodeURIComponent(courseKey)}`, { method: 'POST' });
  await refreshNoteGenStatus();
}

/**
 * Fetch and display the current course note generation status and pause flag.
 * @returns {Promise<void>}
 */
async function refreshNoteGenStatus() {
  const courseKey = document.getElementById('ngCourseKey')?.value.trim();
  if (!courseKey) return;
  const res = await fetch(`/api/notes/status/${encodeURIComponent(courseKey)}`);
  const data = await res.json();
  const banner = document.getElementById('ngStatusBanner');
  if (banner) {
    const count = Object.keys(data.chapters || {}).length;
    banner.textContent = `課程 ${courseKey}：已記錄 ${count} 章${data.paused ? '（已請求暫停）' : ''}`;
  }
  await loadGeneratedChaptersList();
}

/**
 * Load generated `.md` chapter pills for the active course.
 * @returns {Promise<void>}
 */
async function loadGeneratedChaptersList() {
  const courseKey = document.getElementById('ngCourseKey')?.value.trim();
  const host = document.getElementById('ngChaptersList');
  if (!courseKey || !host) return;
  try {
    const res = await fetch(`/api/notes/chapters/${encodeURIComponent(courseKey)}`);
    const data = await res.json();
    const chapters = data.chapters || [];
    host.innerHTML = chapters.length
      ? chapters
          .map(
            (ch) =>
              `<button type="button" class="btn btn-soft btn-sm" onclick="selectGeneratedChapter(${jsAttr(ch.chapter_id)})">${escHtml(ch.chapter_id)} ${escHtml(ch.title)}</button>`,
          )
          .join('')
      : '<span class="small muted">尚無已縫合筆記</span>';
  } catch (err) {
    console.error('Failed to list chapters:', err);
  }
}

/**
 * Select a generated chapter pill and display its stitched `.md` content.
 * @param {string} chapterId Chapter identifier such as `ch01`.
 * @returns {Promise<void>}
 */
async function selectGeneratedChapter(chapterId) {
  const chEl = document.getElementById('ngChapterId');
  if (chEl) chEl.value = chapterId;
  await loadStitchedNoteContent();
}

/**
 * Load and display the stitched chapter Markdown note content.
 * @returns {Promise<void>}
 */
async function loadStitchedNoteContent() {
  const courseKey = document.getElementById('ngCourseKey')?.value.trim();
  const chapterId = document.getElementById('ngChapterId')?.value.trim() || 'ch01';
  if (!courseKey) return;
  const res = await fetch(
    `/api/notes/content/${encodeURIComponent(courseKey)}/${encodeURIComponent(chapterId)}`,
  );
  const data = await res.json();
  const pathEl = document.getElementById('ngNoteFilePath');
  const box = document.getElementById('ngNoteContent');
  if (pathEl) pathEl.textContent = data.exists ? data.path : '尚未產出';
  if (box) box.value = data.content || '';
}

/**
 * Render the current chapter `.md` note to PDF and upload it to Gemini Notebook.
 * @returns {Promise<void>}
 */
async function pushCurrentNoteToNotebook() {
  const courseKey = document.getElementById('ngCourseKey')?.value.trim();
  const chapterId = document.getElementById('ngChapterId')?.value.trim() || 'ch01';
  const notebookId = document.getElementById('ngNotebookId')?.value.trim() || '';
  if (!courseKey) return;
  const banner = document.getElementById('ngStatusBanner');
  if (banner) banner.textContent = `正在將 ${chapterId} 轉為 PDF 並推送至 Gemini Notebook...`;
  try {
    const res = await fetch('/api/notes/push_to_source', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ course_key: courseKey, chapter_id: chapterId, notebook_id: notebookId }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '推送失敗');
    if (banner) banner.textContent = `已推送至 Gemini Notebook（source_id: ${data.source_id}）`;
  } catch (err) {
    if (banner) banner.textContent = `推送錯誤：${err.message}`;
  }
}

document.addEventListener('DOMContentLoaded', initNoteGenPanel);
