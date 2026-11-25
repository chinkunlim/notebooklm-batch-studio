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
 * @returns {Promise<void>}
 */
async function openTextbookSplitFlow(code) {
  try {
    const res = await fetch(`/api/courses/${encodeURIComponent(code)}/textbooks`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const books = data.textbooks || [];
    if (!books.length) { showToast('01 Materials 頂層沒有 PDF 課本。先把整本課本放進 01 Materials/。', 'info', 6000); return; }
    let book = books[0];
    if (books.length > 1) {
      const list = books.map((b, i) => `${i + 1}. ${b.relative_path}${b.split ? '（已切割過）' : ''}`).join('\n');
      const pick = window.prompt(`要切割哪一本？輸入編號：\n\n${list}`, '1');
      book = books[Number(pick) - 1];
      if (!book) return;
    }
    const url = `/api/courses/${encodeURIComponent(code)}/textbooks/split`;
    const preview = await _tbPost(url, { relative_path: book.relative_path, dry_run: true });
    const rows = preview.chapters.map(c => `${c.status === 'exists' ? '（已存在，略過）' : ''}${c.filename}　p.${c.start}-${c.end}`).join('\n');
    const todo = preview.chapters.filter(c => c.status === 'create').length;
    if (!todo) { showToast('所有章節都已切割過，沒有要新增的檔案。', 'info'); return; }
    const msg = `切割「${book.relative_path}」\n輸出到：${preview.output_dir}/\n新增 ${todo} 章（原本整本 PDF 不會動）：\n\n${rows}`;
    if (!(await askConfirm(msg, { okLabel: `切割 ${todo} 章` }))) return;
    await _tbPost(url, { relative_path: book.relative_path, dry_run: false });
    showToast(`已切割 ${todo} 章到 ${preview.output_dir}/`, 'success', 6000);
    await _tbRefresh(code);
  } catch (e) {
    showToast('課本切割失敗：' + e.message, 'error', 7000);
  }
}

/**
 * Move chapter PDFs from 02 Handouts into 01 Materials/<book>/ after a preview (lecture numbers kept).
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function openRelocateHandoutsFlow(code) {
  const name = window.prompt('課本名稱（會建立 01 Materials/<課本名稱>/ 資料夾）：', '');
  if (!name || !name.trim()) return;
  const url = `/api/courses/${encodeURIComponent(code)}/textbooks/relocate-handouts`;
  try {
    const preview = await _tbPost(url, { book_folder: name.trim(), dry_run: true });
    const moves = preview.moves || [];
    if (!moves.length) { showToast('02 Handouts 裡沒有要搬的講次 PDF。', 'info'); return; }
    const conflicts = moves.filter(m => m.status === 'conflict');
    if (conflicts.length) { showToast(`目的地已有同名檔案，未搬移：\n${conflicts.map(m => m.to).join('\n')}`, 'error', 8000); return; }
    const list = moves.map(m => `L${m.no}　${m.filename}`).join('\n');
    const msg = `把 ${moves.length} 個章節 PDF 從 02 Handouts 搬到：\n${preview.destination}/\n\n${list}\n\n講次編號、已上傳的來源與已完成的產出都不會改變。`;
    if (!(await askConfirm(msg, { okLabel: `搬移 ${moves.length} 個檔案` }))) return;
    await _tbPost(url, { book_folder: name.trim(), dry_run: false });
    showToast(`已搬到 ${preview.destination}/`, 'success', 6000);
    await _tbRefresh(code);
  } catch (e) {
    showToast('搬移失敗：' + e.message, 'error', 7000);
  }
}
