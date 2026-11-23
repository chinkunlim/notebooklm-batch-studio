/**
 * Phase 1 modular Markdown note generation UI controller (Refs: ADR-012).
 */

let _ngPromptsCache = [];

/**
 * Load standalone modular prompt template metadata and populate the step selector.
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
        .map((p) => `<option value="${p.step_id}">${p.step_id} — ${p.title}</option>`)
        .join('');
      await previewNotePrompt();
    }
  } catch (err) {
    console.error('Failed to load note prompt specs:', err);
  }
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

document.addEventListener('DOMContentLoaded', initNoteGenPanel);
