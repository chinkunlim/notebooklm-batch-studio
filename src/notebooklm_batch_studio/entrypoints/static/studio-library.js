/**
 * Study-library web actions (SPEC-016): register past / non-standard course folders, scratch filing,
 * unfiling, and course display-name changes. Uses helpers from studio-escape.js, studio-core.js,
 * studio-app.js and studio-record.js (escHtml, jsAttr, showToast, askConfirm, fetchCourses).
 */

const _LIB_ROLES = ['materials', 'handouts', 'notes', 'homework', 'assignments'];

/**
 * Send a JSON request and return the parsed body, throwing the server's `detail` on failure.
 * @param {string} url Endpoint URL
 * @param {string} method HTTP method
 * @param {object} [body] JSON payload
 * @returns {Promise<object>} Parsed JSON response
 */
async function _libJson(url, method, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

/**
 * Refresh course lists and the learning record after a library change.
 * @returns {Promise<void>}
 */
async function _libRefresh() {
  if (typeof fetchCourses === 'function') await fetchCourses();
  if (typeof loadLearningRecordView === 'function') await loadLearningRecordView();
}

/**
 * Buttons shown on an unregistered course card in 學習紀錄.
 * @param {object} course CourseRecordView payload with status 'unregistered'
 * @returns {string} HTML
 */
function libraryRegisterButtonsHtml(course) {
  const id = `libArchive_${String(course.code).replace(/[^A-Za-z0-9_-]/g, '_')}`;
  return `<div class="row" style="gap:8px;align-items:center;margin:6px 0">
    <button class="btn btn-soft btn-sm" onclick="registerLibraryCourses([${jsAttr(course.code)}], document.getElementById('${id}').checked)">登錄</button>
    <label class="small"><input type="checkbox" id="${id}" checked> 同時封存（舊學期建議勾選）</label>
  </div>`;
}

/**
 * Term-level actions: batch register unregistered courses and manually register other folders.
 * @param {object} term TermRecordView payload
 * @returns {string} HTML
 */
function libraryTermActionsHtml(term) {
  const pending = (term.courses || []).filter(c => c.status === 'unregistered').map(c => c.code);
  const batch = pending.length
    ? `<button class="btn btn-soft btn-sm" onclick='registerLibraryCourses(${JSON.stringify(pending)}, true)'>登錄本學期所有未登錄課程（${pending.length}）</button>`
    : '';
  const others = (term.others || []).map(name =>
    `<span class="row" style="gap:4px;align-items:center">${escHtml(name)}<button class="btn btn-ghost btn-sm" onclick="registerLibraryFolder(${jsAttr(term.term)}, ${jsAttr(name)})">手動登錄…</button></span>`
  ).join('');
  const othersHtml = others ? `<div class="small muted row" style="gap:10px;flex-wrap:wrap;margin-top:6px">其他資料夾／檔案：${others}</div>` : '';
  return (batch ? `<div style="margin:4px 0 10px">${batch}</div>` : '') + othersHtml;
}

/**
 * Register scanned course folders in record-only mode (no jobs, no Gemini Notebook quota).
 * @param {Array<string>} codes Course codes
 * @param {boolean} archive Whether to archive them at the same time
 * @returns {Promise<void>}
 */
async function registerLibraryCourses(codes, archive) {
  const msg = `登錄 ${codes.length} 門課程為「只記錄」課程${archive ? '並封存' : ''}？\n\n${codes.join('\n')}\n\n不會產生任何內容，也不會使用 Gemini Notebook 額度。`;
  if (!(await askConfirm(msg, { okLabel: '登錄' }))) return;
  try {
    const data = await _libJson('/api/study/library/register', 'POST', { codes, archive });
    const ok = (data.results || []).filter(r => !r.skipped).length;
    showToast(`已登錄 ${ok} / ${codes.length} 門課程`, 'success');
    await _libRefresh();
  } catch (e) {
    showToast('登錄失敗：' + e.message, 'error');
  }
}

/**
 * Manually register a non-standard folder under study/<term>/ with a typed course number.
 * @param {string} term Academic term
 * @param {string} folder Folder basename
 * @returns {Promise<void>}
 */
async function registerLibraryFolder(term, folder) {
  const courseNo = window.prompt(`為「${term}/${folder}」輸入課號（例：CP30000）：`, '');
  if (!courseNo || !courseNo.trim()) return;
  try {
    const data = await _libJson('/api/study/library/register-folder', 'POST', { term, folder, course_no: courseNo.trim() });
    showToast(`已登錄 ${data.code || folder}`, 'success');
    await _libRefresh();
  } catch (e) {
    showToast('手動登錄失敗：' + e.message, 'error');
  }
}

/**
 * Small "撤銷歸檔" button for one file inside a registered course category.
 * @param {object} course CourseRecordView payload (needs study_dir)
 * @param {string} rel File path relative to the course folder
 * @returns {string} HTML
 */
function libraryUnfileButtonHtml(course, rel) {
  if (!course.study_dir || course.status === 'unregistered') return '';
  const abs = `${course.study_dir}/${rel}`;
  return ` <button class="btn btn-ghost btn-sm" onclick="unfileLibraryItem(${jsAttr(abs)})">撤銷歸檔</button>`;
}

/**
 * Move a course file back to scratch/unarchived/<code>/ after confirmation.
 * @param {string} path Absolute file path
 * @returns {Promise<void>}
 */
async function unfileLibraryItem(path) {
  if (!(await askConfirm(`把這個檔案移回 scratch/unarchived/？\n\n${path}`, { okLabel: '撤銷歸檔' }))) return;
  try {
    const data = await _libJson('/api/study/unfile', 'POST', { path });
    showToast(`已移到：${data.dest}`, 'success', 6000);
    await _libRefresh();
  } catch (e) {
    showToast('撤銷歸檔失敗：' + e.message, 'error');
  }
}

/**
 * Render the "未歸檔檔案" card listing scratch/ items with course + category pickers.
 * @returns {Promise<void>}
 */
async function loadUnfiledCard() {
  const host = document.getElementById('unfiledCard');
  if (!host) return;
  try {
    const data = await _libJson('/api/study/unfiled', 'GET');
    const items = data.items || [];
    if (!items.length) { host.innerHTML = ''; return; }
    const courses = (typeof currentCoursesList !== 'undefined' && currentCoursesList) ? currentCoursesList : [];
    const courseOpts = courses.map(c => `<option value="${escHtml(c.code)}">${escHtml(c.code)}　${escHtml(c.name)}</option>`).join('');
    const names = window.STUDY_CATEGORY_NAMES || {};
    const roleOpts = _LIB_ROLES.map(r => `<option value="${r}">${escHtml(names[r] || r)}</option>`).join('');
    host.innerHTML = `<article class="card" style="margin-bottom:16px"><div class="card-head"><b>未歸檔檔案（scratch/）</b><span class="small muted">${items.length} 個</span></div>
      ${items.map((it, i) => `<div class="row" style="gap:8px;flex-wrap:wrap;align-items:center;padding:6px 0;border-bottom:1px solid var(--border)">
        <span class="small" style="min-width:0;flex:1;word-break:break-all">${escHtml(it.relative_path || it.name)}</span>
        <select id="unfCourse${i}" class="select">${courseOpts}</select>
        <select id="unfRole${i}" class="select">${roleOpts}</select>
        <button class="btn btn-soft btn-sm" onclick="fileLibraryItem(${jsAttr(it.path)}, ${i})">歸檔</button></div>`).join('')}
    </article>`;
  } catch (e) {
    host.innerHTML = '';
    console.warn('Could not load unfiled items:', e);
  }
}

/**
 * File one scratch item into the chosen course category.
 * @param {string} path Absolute scratch file path
 * @param {number} idx Row index used to read the pickers
 * @returns {Promise<void>}
 */
async function fileLibraryItem(path, idx) {
  const courseCode = document.getElementById(`unfCourse${idx}`)?.value;
  const role = document.getElementById(`unfRole${idx}`)?.value;
  if (!courseCode || !role) { showToast('請先選擇課程與分類', 'error'); return; }
  try {
    const data = await _libJson('/api/study/file', 'POST', { path, course_code: courseCode, role });
    showToast(`已歸檔到：${data.dest}`, 'success', 6000);
    await _libRefresh();
    await loadUnfiledCard();
  } catch (e) {
    showToast('歸檔失敗：' + e.message, 'error');
  }
}

/**
 * Ask for a new display name and save it (code, subject and folder stay unchanged).
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function openCourseDisplayNameFlow(code) {
  const current = ((typeof currentCoursesList !== 'undefined' && currentCoursesList) || []).find(c => c.code === code);
  const input = window.prompt(`「${code}」的新課程名稱（課程代碼與資料夾不會改變）：`, current ? current.name : '');
  if (input === null || !input.trim() || (current && input.trim() === current.name)) return;
  try {
    const data = await _libJson(`/api/courses/${encodeURIComponent(code)}/name`, 'PUT', { name: input.trim() });
    showToast(`課程名稱已改為「${data.name}」`, 'success');
    await _libRefresh();
    if (typeof viewCourseDetail === 'function' && typeof activeCourseCode !== 'undefined' && activeCourseCode === code) {
      await viewCourseDetail(code, true);
    }
    if (typeof initStudyPortal === 'function') await initStudyPortal();
  } catch (e) {
    showToast('修改課程名稱失敗：' + e.message, 'error');
  }
}

/**
 * Format a byte count as MB with one decimal.
 * @param {number} bytes Size in bytes
 * @returns {string} Human-readable size
 */
function _libMb(bytes) {
  return `${((bytes || 0) / 1048576).toFixed(1)} MB`;
}

/**
 * Render the database backup list in 設計與自訂 (SPEC-017).
 * @returns {Promise<void>}
 */
async function loadBackupsCard() {
  const host = document.getElementById('backupsList');
  if (!host) return;
  try {
    const data = await _libJson('/api/system/backups', 'GET');
    const rows = data.backups || [];
    const total = rows.reduce((sum, b) => sum + (b.size_bytes || 0), 0);
    host.innerHTML = rows.length
      ? `<div class="small muted">共 ${rows.length} 份，${_libMb(total)}</div>` +
        rows.map(b => `<div class="small num">${escHtml(b.name)}　${_libMb(b.size_bytes)}</div>`).join('')
      : '<div class="small muted">目前沒有備份。</div>';
  } catch (e) {
    host.innerHTML = `<div class="small muted">${escHtml(e.message || '載入失敗')}</div>`;
  }
}

/**
 * Preview, confirm, then move backups older than the newest `keep` into deleted/backups/.
 * @param {number} keep Number of newest backups to keep
 * @returns {Promise<void>}
 */
async function pruneOldBackups(keep) {
  try {
    const preview = await _libJson('/api/system/backups/prune', 'POST', { keep, dry_run: true });
    if (!(preview.to_move || []).length) { showToast(`目前不到 ${keep} 份以上，不需要整理`, 'info'); return; }
    const msg = `保留最新 ${keep} 份，把 ${preview.to_move.length} 份舊備份移到：\n${preview.destination}\n\n${preview.to_move.join('\n')}\n\n只會搬移，不會刪除。`;
    if (!(await askConfirm(msg, { okLabel: '移走舊備份' }))) return;
    const done = await _libJson('/api/system/backups/prune', 'POST', { keep, dry_run: false });
    showToast(`已移走 ${(done.moved || []).length} 份舊備份`, 'success');
    await loadBackupsCard();
  } catch (e) {
    showToast('整理備份失敗：' + e.message, 'error');
  }
}

window.loadBackupsCard = loadBackupsCard;

