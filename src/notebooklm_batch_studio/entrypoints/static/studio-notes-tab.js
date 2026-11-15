/* Gemini Notebook 學習工作室 — Full QA Notes Studio tab: 4-dimension hierarchical tag filtering,
   cross-course keyword search, mastery toggling, Markdown copy, inline personal memo editing,
   and single or bundled PDF push back to Gemini Notebook sources. */

const qaNotesState = {
  notes: [],
  tagFilter: '',
  masteryFilter: '',
  crossCourse: false,
  selectedIds: new Set(),
};

/**
 * Load notes from the backend using current filters and render the QA Notes panel.
 * @returns {Promise<void>} Resolves when rendered
 */
async function loadCourseNotes() {
  const container = document.getElementById('qaNotesContainer');
  if (!container || typeof currentStudyCourse === 'undefined' || !currentStudyCourse) return;
  const code = qaNotesState.crossCourse ? '*' : currentStudyCourse.code;
  const params = new URLSearchParams();
  if (qaNotesState.tagFilter.trim()) params.set('tag', qaNotesState.tagFilter.trim());
  if (qaNotesState.masteryFilter) params.set('mastery', qaNotesState.masteryFilter);
  const qs = params.toString() ? `?${params.toString()}` : '';
  try {
    const res = await fetch(`/api/courses/${code}/notes` + qs);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    qaNotesState.notes = data.notes || [];
    renderQaNotesPanel();
  } catch (err) {
    container.innerHTML = `<div class="empty-state">無法載入問答筆記：${escHtml(err.message)}</div>`;
  }
}

/**
 * Render the toolbar, tag cloud pills, and note cards inside `#qaNotesContainer`.
 * @returns {void}
 */
function renderQaNotesPanel() {
  const container = document.getElementById('qaNotesContainer');
  if (!container) return;
  const head = document.getElementById('qaNotesHead');
  const toolbar = renderNotesToolbar();
  if (head) head.innerHTML = toolbar;
  const tagCloud = renderNotesTagCloud();
  const cards = qaNotesState.notes.length
    ? qaNotesState.notes.map(n => renderOneNoteCard(n)).join('')
    : '<div class="empty-state">目前沒有符合條件的筆記。可按 <b>⌘J</b> 提問後一鍵整理，或在測驗解析點「收錄為問答筆記」。</div>';
  container.innerHTML = `${head ? '' : toolbar}${tagCloud}<div id="qaNotesList">${cards}</div>`;
}

/**
 * Build HTML for the search, cross-course, mastery filter, and bundle actions toolbar.
 * @returns {string} Toolbar HTML
 */
function renderNotesToolbar() {
  const count = qaNotesState.selectedIds.size;
  return `<div class="qa-notes-toolbar">
    <input type="text" id="qaNotesSearchInput" class="text-input" value="${escHtml(qaNotesState.tagFilter)}" placeholder="搜尋標籤或關鍵字（如 進化論、L03）" onkeydown="if(event.key==='Enter')applyNotesSearch()">
    <button type="button" class="reader-pill-btn" onclick="applyNotesSearch()">搜尋</button>
    <label class="qa-cross-label"><input type="checkbox" ${qaNotesState.crossCourse ? 'checked' : ''} onchange="toggleNotesCrossCourse(this.checked)"> 跨課程</label>
    <select class="text-input" onchange="changeNotesMasteryFilter(this.value)">
      <option value="" ${qaNotesState.masteryFilter === '' ? 'selected' : ''}>全部掌握度</option>
      <option value="needs_review" ${qaNotesState.masteryFilter === 'needs_review' ? 'selected' : ''}>待加強</option>
      <option value="mastered" ${qaNotesState.masteryFilter === 'mastered' ? 'selected' : ''}>已搞懂</option>
    </select>
    <button type="button" class="reader-pill-btn" ${count ? '' : 'disabled'} onclick="bundleSelectedNotesToSource()">打包勾選 (${count})</button>
  </div>`;
}

/**
 * Build clickable tag pills extracted from the currently loaded notes.
 * @returns {string} Tag cloud HTML
 */
function renderNotesTagCloud() {
  const counts = new Map();
  qaNotesState.notes.forEach(n => (n.tags || []).forEach(t => counts.set(t, (counts.get(t) || 0) + 1)));
  if (!counts.size) return '';
  const pills = [...counts.entries()].slice(0, 24).map(([tag, cnt]) => {
    const active = qaNotesState.tagFilter === tag ? ' on' : '';
    return `<button type="button" class="qa-tag-pill${active}" onclick="selectNotesTagPill('${escHtml(tag)}')">${escHtml(tag)} (${cnt})</button>`;
  }).join('');
  return `<div class="qa-tag-pills">${pills}</div>`;
}

/**
 * Build HTML for a single QA note card with actions, tags, and memo editor.
 * @param {object} note Note record from API
 * @returns {string} Card HTML
 */
function renderOneNoteCard(note) {
  const checked = qaNotesState.selectedIds.has(note.id) ? 'checked' : '';
  const lecLabel = note.lecture_no ? `L${String(note.lecture_no).padStart(2, '0')}` : '全課程';
  const nextStatus = note.mastery_status === 'mastered' ? 'needs_review' : 'mastered';
  const masteryLabel = note.mastery_status === 'mastered' ? '已搞懂' : '待加強';
  const sourceBadge = note.is_uploaded_as_source ? '<span class="tag ok">已回灌來源</span>' : '';
  const tagsHtml = (note.tags || []).map(t => `<button type="button" class="qa-tag-pill" onclick="selectNotesTagPill('${escHtml(t)}')">${escHtml(t)}</button>`).join('');
  return `<article class="qa-note-card" data-note-id="${escHtml(note.id)}">
    <div class="qa-note-card-head">
      <label class="row" style="gap:8px;align-items:center">
        <input type="checkbox" ${checked} onchange="toggleNoteSelection('${escHtml(note.id)}', this.checked)">
        <strong>${escHtml(note.title)}</strong>
        <span class="tag">${escHtml(note.course_code)} · ${lecLabel}</span>${sourceBadge}
      </label>
      <div class="row" style="gap:6px">
        <button type="button" class="btn btn-soft btn-sm" onclick="toggleNoteMastery('${escHtml(note.course_code)}','${escHtml(note.id)}','${nextStatus}')">${masteryLabel}</button>
        <button type="button" class="btn btn-ghost btn-sm" onclick="copyNoteMarkdown('${escHtml(note.id)}')">複製 MD</button>
        <button type="button" class="btn btn-soft btn-sm" onclick="pushSingleNoteToSource('${escHtml(note.course_code)}','${escHtml(note.id)}')">回灌來源</button>
        <button type="button" class="btn btn-ghost btn-sm" onclick="deleteCourseNote('${escHtml(note.course_code)}','${escHtml(note.id)}')">刪除</button>
      </div>
    </div>
    <div class="qa-tag-pills">${tagsHtml}</div>
    <div class="small" style="white-space:pre-wrap;line-height:1.5">${escHtml(note.content_markdown || '')}</div>
    <div class="row" style="gap:8px;align-items:center">
      <input type="text" class="text-input" id="memo-${escHtml(note.id)}" value="${escHtml(note.personal_memo || '')}" placeholder="新增或編輯個人心得…" style="flex:1;font-size:13px">
      <button type="button" class="btn btn-soft btn-sm" onclick="saveNoteMemo('${escHtml(note.course_code)}','${escHtml(note.id)}')">儲存心得</button>
    </div>
  </article>`;
}

/**
 * Apply the keyword/tag filter from the search input and reload notes.
 * @returns {void}
 */
function applyNotesSearch() {
  qaNotesState.tagFilter = document.getElementById('qaNotesSearchInput')?.value || '';
  loadCourseNotes();
}

/**
 * Toggle cross-course search mode and reload notes.
 * @param {boolean} enabled Whether cross-course mode is enabled
 * @returns {void}
 */
function toggleNotesCrossCourse(enabled) {
  qaNotesState.crossCourse = Boolean(enabled);
  loadCourseNotes();
}

/**
 * Filter notes by mastery status and reload.
 * @param {string} status Empty string, 'needs_review', or 'mastered'
 * @returns {void}
 */
function changeNotesMasteryFilter(status) {
  qaNotesState.masteryFilter = status || '';
  loadCourseNotes();
}

/**
 * Toggle a tag pill filter on or off and reload notes.
 * @param {string} tag Tag string
 * @returns {void}
 */
function selectNotesTagPill(tag) {
  qaNotesState.tagFilter = qaNotesState.tagFilter === tag ? '' : tag;
  loadCourseNotes();
}

/**
 * Track checkbox selection for multi-note PDF bundling.
 * @param {string} noteId Note identifier
 * @param {boolean} selected Checked state
 * @returns {void}
 */
function toggleNoteSelection(noteId, selected) {
  if (selected) qaNotesState.selectedIds.add(noteId);
  else qaNotesState.selectedIds.delete(noteId);
  renderQaNotesPanel();
}

/**
 * Copy a note's Markdown content to the clipboard.
 * @param {string} noteId Note identifier
 * @returns {Promise<void>} Resolves when copied
 */
async function copyNoteMarkdown(noteId) {
  const note = qaNotesState.notes.find(n => n.id === noteId);
  if (!note) return;
  try {
    await navigator.clipboard.writeText(note.content_markdown || '');
    showToast('已複製 Markdown 內容', 'success', 1800);
  } catch (err) {
    showToast('無法寫入剪貼簿', 'error');
  }
}

/**
 * Toggle a note's mastery status via PATCH endpoint.
 * @param {string} code Course code
 * @param {string} noteId Note identifier
 * @param {string} status Target mastery status
 * @returns {Promise<void>} Resolves when updated
 */
async function toggleNoteMastery(code, noteId, status) {
  const res = await fetch(`/api/courses/${code}/notes/${noteId}/mastery`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
  if (res.ok) loadCourseNotes();
  else showToast('更新掌握度失敗', 'error');
}

/**
 * Save personal memo text for a note via PATCH endpoint.
 * @param {string} code Course code
 * @param {string} noteId Note identifier
 * @returns {Promise<void>} Resolves when saved
 */
async function saveNoteMemo(code, noteId) {
  const memo = document.getElementById(`memo-${noteId}`)?.value || '';
  const res = await fetch(`/api/courses/${code}/notes/${noteId}/memo`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ personal_memo: memo }),
  });
  if (res.ok) {
    showToast('已儲存個人心得', 'success', 1800);
    loadCourseNotes();
  } else {
    showToast('儲存心得失敗', 'error');
  }
}

/**
 * Push a single note as a PDF back to Gemini Notebook sources.
 * @param {string} code Course code
 * @param {string} noteId Note identifier
 * @returns {Promise<void>} Resolves when pushed
 */
async function pushSingleNoteToSource(code, noteId) {
  const res = await fetch(`/api/courses/${code}/notes/${noteId}/push_to_source`, { method: 'POST' });
  const data = await res.json();
  if (res.ok) {
    showToast('已將筆記轉換為 PDF 並回灌至 Gemini 來源', 'success', 2600);
    loadCourseNotes();
  } else {
    showToast(`回灌失敗：${data.detail || res.statusText}`, 'error');
  }
}

/**
 * Bundle all checked notes into one PDF and upload it to Gemini Notebook sources.
 * @returns {Promise<void>} Resolves when bundled and uploaded
 */
async function bundleSelectedNotesToSource() {
  if (!qaNotesState.selectedIds.size || typeof currentStudyCourse === 'undefined' || !currentStudyCourse) return;
  const noteIds = [...qaNotesState.selectedIds];
  const res = await fetch(`/api/courses/${currentStudyCourse.code}/notes/bundle_to_source`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note_ids: noteIds, title: '問答筆記精選合輯' }),
  });
  const data = await res.json();
  if (res.ok) {
    qaNotesState.selectedIds.clear();
    showToast(`已打包 ${data.bundled_count} 則筆記並回灌來源`, 'success', 2600);
    loadCourseNotes();
  } else {
    showToast(`打包回灌失敗：${data.detail || res.statusText}`, 'error');
  }
}

/**
 * Delete a note from the course library.
 * @param {string} code Course code
 * @param {string} noteId Note identifier
 * @returns {Promise<void>} Resolves when deleted
 */
async function deleteCourseNote(code, noteId) {
  const res = await fetch(`/api/courses/${code}/notes/${noteId}`, { method: 'DELETE' });
  if (res.ok) {
    qaNotesState.selectedIds.delete(noteId);
    showToast('已刪除筆記', 'info', 1800);
    loadCourseNotes();
  } else {
    showToast('刪除失敗', 'error');
  }
}
