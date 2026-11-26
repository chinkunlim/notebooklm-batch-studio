/**
 * Textbook tools in the course's advanced menu (SPEC-018): split a 01 Materials textbook into chapter
 * PDFs, and move chapter PDFs that were filed in 02 Handouts into 01 Materials/<book>/.
 * Uses helpers from studio-escape.js, studio-core.js and studio-batch.js (showToast, askConfirm, viewCourseDetail).
 */

/**
 * POST JSON to a textbook endpoint and return the parsed body (throws the server's `detail`).
 * @param {string} url Endpoint URL
 * @param {object} body JSON payload
 * @returns {Promise<object>} Parsed response
 */
async function _tbPost(url, body) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

/**
 * Refresh the open course page after a textbook change.
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function _tbRefresh(code) {
  if (typeof fetchCourses === 'function') await fetchCourses();
  if (typeof viewCourseDetail === 'function') await viewCourseDetail(code, true);
}

/**
 * Pick a textbook from 01 Materials, preview its chapters, then split after confirmation.
 * @param {string} code Course code
 * @param {string} [relativePath] Book to split directly (from the detection card)
 * @returns {Promise<void>}
 */
async function openTextbookSplitFlow(code, relativePath) {
  try {
    const res = await fetch(`/api/courses/${encodeURIComponent(code)}/textbooks`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const books = data.textbooks || [];
    if (!books.length) { showToast('01 Materials 頂層沒有 PDF 課本。先把整本課本放進 01 Materials/。', 'info', 6000); return; }
    let book = relativePath ? books.find(b => b.relative_path === relativePath) : books[0];
    if (!book) return;
    if (!relativePath && books.length > 1) {
      const options = books.map(b => ({ value: b.relative_path, label: `${b.relative_path}${b.split ? '（已切割過）' : ''}` }));
      const chosen = await askPick('要切割哪一本課本？', options, { okLabel: '預覽章節' });
      book = books.find(b => b.relative_path === chosen);
      if (!book) return;
    }
    const url = `/api/courses/${encodeURIComponent(code)}/textbooks/split`;
    let preview = await _tbPost(url, { relative_path: book.relative_path, dry_run: true });
    let target_folder = '';
    if (preview.needs_folder_choice) {
      // Several textbook folders in this course: the user picks where the chapters go (SPEC-025 R3).
      const suggested = String(preview.output_dir).split('/').pop();
      const ordered = [...preview.folder_choices].sort((a, b) => (b.name === suggested) - (a.name === suggested));
      const options = ordered.map(c => ({ value: c.name, label: `${c.name}（已有 ${c.chapters} 章）${c.name === suggested ? '　建議' : ''}` }));
      target_folder = await askPick('這門課有多個課本資料夾，要切割到哪一個？', options, { okLabel: '預覽章節' });
      if (!target_folder) return;
      preview = await _tbPost(url, { relative_path: book.relative_path, dry_run: true, target_folder });
    }
    const rows = preview.chapters.map(c => `${c.status === 'exists' ? '（已存在，略過）' : ''}${c.filename}　p.${c.start}-${c.end}`).join('\n');
    const todo = preview.chapters.filter(c => c.status === 'create').length;
    if (!todo) { showToast('所有章節都已切割過，沒有要新增的檔案。', 'info'); return; }
    const msg = `切割「${book.relative_path}」\n輸出到：${preview.output_dir}/\n新增 ${todo} 章（原本整本 PDF 不會動）：\n\n${rows}`;
    if (!(await askConfirm(msg, { okLabel: `切割 ${todo} 章` }))) return;
    await _tbPost(url, { relative_path: book.relative_path, dry_run: false, target_folder });
    showToast(`已切割 ${todo} 章到 ${preview.output_dir}/`, 'success', 6000);
    await _tbRefresh(code);
    await loadPendingTextbooks();
  } catch (e) {
    showToast('課本切割失敗：' + e.message, 'error', 7000);
  }
}

/**
 * Choose the textbook folder inside 01 Materials from existing folders and textbook PDFs, or name a new one.
 * @param {string} code Course code
 * @returns {Promise<string|null>} Folder name, or null when cancelled
 */
async function _pickBookFolder(code) {
  const enc = encodeURIComponent(code);
  const [subs, books] = await Promise.all([
    fetch(`/api/courses/${enc}/subfolders?category=${encodeURIComponent('01 Materials')}`).then(r => (r.ok ? r.json() : {})),
    fetch(`/api/courses/${enc}/textbooks`).then(r => (r.ok ? r.json() : {})),
  ]);
  const names = new Set(subs.subfolders || []);
  (books.textbooks || []).forEach(b => names.add(String(b.chapters_folder).split('/').pop()));
  names.delete('Literature_Review');
  if (!names.size) return _askNewFolderName();
  const options = [...names].sort().map(n => ({ value: n, label: n }));
  return askPick('把章節搬到 01 Materials 的哪個課本資料夾？', options, { okLabel: '預覽搬移', allowNew: true });
}

/**
 * Move chapter PDFs from 02 Handouts into 01 Materials/<book>/ after a preview (lecture numbers kept).
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function openRelocateHandoutsFlow(code) {
  const name = await _pickBookFolder(code);
  if (!name) return;
  const url = `/api/courses/${encodeURIComponent(code)}/textbooks/relocate-handouts`;
  try {
    const preview = await _tbPost(url, { book_folder: name, dry_run: true });
    const moves = preview.moves || [];
    if (!moves.length) { showToast('02 Handouts 裡沒有要搬的講次 PDF。', 'info'); return; }
    const conflicts = moves.filter(m => m.status === 'conflict');
    if (conflicts.length) { showToast(`目的地已有同名檔案，未搬移：\n${conflicts.map(m => m.to).join('\n')}`, 'error', 8000); return; }
    const list = moves.map(m => `L${m.no}　${m.filename}`).join('\n');
    const msg = `把 ${moves.length} 個章節 PDF 從 02 Handouts 搬到：\n${preview.destination}/\n\n${list}\n\n講次編號、已上傳的來源與已完成的產出都不會改變。`;
    if (!(await askConfirm(msg, { okLabel: `搬移 ${moves.length} 個檔案` }))) return;
    await _tbPost(url, { book_folder: name, dry_run: false });
    showToast(`已搬到 ${preview.destination}/`, 'success', 6000);
    await _tbRefresh(code);
  } catch (e) {
    showToast('搬移失敗：' + e.message, 'error', 7000);
  }
}

/**
 * Keys of detected textbooks the user chose to ignore (saved in local preferences).
 * @returns {Array<string>} `code|relative_path` keys
 */
function _dismissedTextbooks() {
  try { return JSON.parse(prefLoad('textbookDismissed', '[]')) || []; } catch (e) { return []; }
}

/**
 * Stop showing one detected textbook.
 * @param {string} code Course code
 * @param {string} relativePath Book path inside the course
 * @returns {Promise<void>}
 */
async function dismissPendingTextbook(code, relativePath) {
  const keys = new Set(_dismissedTextbooks());
  keys.add(`${code}|${relativePath}`);
  prefSave('textbookDismissed', JSON.stringify([...keys]));
  await loadPendingTextbooks();
  await loadNewCourseFolders();
}

/**
 * Dismiss key for an ignored-handouts notice; new files bring the notice back.
 * @param {{course_code: string, files: Array<string>}} r Row from `ignored_handouts`
 * @returns {string} Key stored with the dismissed textbooks
 */
function _handoutKey(r) {
  return `${r.course_code}|handouts:${(r.files || []).join(',')}`;
}

/**
 * Card telling the user that 02 Handouts PDFs are not lectures in a textbook course (SPEC-025 R4a).
 * @param {{course_code: string, course_name: string, files: Array<string>}} r Row from `ignored_handouts`
 * @returns {string} Card HTML
 */
function _ignoredHandoutCard(r) {
  const names = r.files.map(f => escHtml(String(f).split('/').pop())).join('、');
  return `<article class="card" style="margin-bottom:12px"><div class="row" style="justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
    <div style="min-width:0"><b>偵測到講義，但本課以課本章節為講次</b>（${escHtml(r.course_name)}）<br>
    <span class="small muted">02 Handouts 的 ${r.files.length} 份 PDF 不會變成講次、也不會排程：${names}</span></div>
    <button class="btn btn-ghost btn-sm" onclick="dismissPendingTextbook(${jsAttr(r.course_code)}, ${jsAttr('handouts:' + r.files.join(','))})">知道了</button>
  </div></article>`;
}

/**
 * Show a card on 批次排程 for every textbook found in 01 Materials that has not been split (SPEC-020).
 * @returns {Promise<void>}
 */
async function loadPendingTextbooks() {
  const host = document.getElementById('textbookPendingHost');
  if (!host) return;
  try {
    const res = await fetch('/api/textbooks/pending');
    if (!res.ok) return;
    const skip = new Set(_dismissedTextbooks());
    const data = await res.json();
    const rows = (data.pending || []).filter(r => !skip.has(`${r.course_code}|${r.relative_path}`));
    const ignored = (data.ignored_handouts || []).filter(r => !skip.has(_handoutKey(r)));
    host.innerHTML = ignored.map(_ignoredHandoutCard).join('') + rows.map(r => {
      const name = String(r.relative_path).split('/').pop();
      const info = r.error
        ? `<span class="small muted">${escHtml(r.error)}</span>`
        : `<span class="small muted">${r.chapters} 章${r.existing ? `，${r.existing} 章已存在（會略過）` : ''}</span>`;
      const splitBtn = r.error ? '' : `<button class="btn btn-primary btn-sm" onclick="openTextbookSplitFlow(${jsAttr(r.course_code)}, ${jsAttr(r.relative_path)})">預覽並切割</button>`;
      return `<article class="card" style="margin-bottom:12px"><div class="row" style="justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
        <div style="min-width:0"><b>偵測到課本：${escHtml(name)}</b>（${escHtml(r.course_name)}）<br>${info}</div>
        <div class="row" style="gap:8px">${splitBtn}<button class="btn btn-ghost btn-sm" onclick="dismissPendingTextbook(${jsAttr(r.course_code)}, ${jsAttr(r.relative_path)})">略過</button></div>
      </div></article>`;
    }).join('');
  } catch (e) {
    console.warn('Could not check for new textbooks:', e);
  }
}

/**
 * Show a card on 批次排程 for every subject folder created or pasted under study/<term>/ but not added yet
 * (SPEC-027/028; folders without a course number say 需要課號 → typed in the wizard). The button opens the
 * add-course wizard with the folder already picked; nothing is scheduled.
 * @returns {Promise<void>}
 */
async function loadNewCourseFolders() {
  const host = document.getElementById('newCourseFolderHost');
  if (!host) return;
  try {
    const res = await fetch('/api/study/new-course-folders');
    if (!res.ok) return;
    const skip = new Set(_dismissedTextbooks());
    const rows = ((await res.json()).folders || []).filter(f => !skip.has(`newcourse|${f.path}`));
    host.innerHTML = rows.map(f => `<article class="card" style="margin-bottom:12px"><div class="row" style="justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center">
      <div style="min-width:0"><b>偵測到新課程資料夾：${escHtml(f.folder)}</b>（${escHtml(f.term)}）<br>
      <span class="small muted">${f.lecture_count} 份講義 PDF・${f.needs_course_no ? '需要課號（加入時填寫）・' : ''}還沒加入，加入後才會排程</span></div>
      <div class="row" style="gap:8px"><button class="btn btn-primary btn-sm" onclick="openAddCourseForFolder(${jsAttr(f.path)})">加入課程…</button>
      <button class="btn btn-ghost btn-sm" onclick="dismissPendingTextbook('newcourse', ${jsAttr(f.path)})">略過</button></div>
    </div></article>`).join('');
  } catch (e) {
    console.warn('Could not check for new course folders:', e);
  }
}

/**
 * Open the add-course wizard with one folder already picked.
 * @param {string} path Absolute course folder path
 */
function openAddCourseForFolder(path) {
  openAddModal();
  pickedFolders = [];
  addPickedFolder(path);
}

document.addEventListener('DOMContentLoaded', () => {
  loadPendingTextbooks();
  loadNewCourseFolders();
  setInterval(() => { loadPendingTextbooks(); loadNewCourseFolders(); }, 60000);
});

