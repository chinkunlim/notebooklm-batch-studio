/**
 * Path pickers (project rule 2026-11-25): every file or folder path on the page is chosen from a list.
 * - `loadSubfolderOptions` / `onSubfolderPick`: <select> of existing subfolders + 「＋ 新增資料夾…」.
 * - `askPick`: in-page dialog with a <select>, used where a choice is needed inside a flow.
 * - Literature pickers refresh automatically when the course or category changes.
 * Uses escHtml (studio-escape.js) and showToast (studio.js).
 */

const PICK_NEW = '__new__';
const _PICK_NEW_LABEL = '＋ 新增資料夾…';

/**
 * Ask for a NEW folder name (the only typed field the path rule allows) and validate it.
 * @returns {string|null} Folder name, or null when cancelled or invalid
 */
function _askNewFolderName() {
  const name = (window.prompt('新資料夾名稱（不可含 / 或 \\，不可用 . 開頭）：', '') || '').trim();
  if (!name) return null;
  if (/[\\/]/.test(name) || name.startsWith('.') || name.length > 128) {
    showToast('資料夾名稱不可含 / 或 \\、不可用 . 開頭、最長 128 字', 'error');
    return null;
  }
  return name;
}

/**
 * Fill a <select> with the existing subfolders of `<course>/<category>/` plus a "new folder" option.
 * @param {HTMLSelectElement} sel Target select
 * @param {string} code Course code ('' = no course chosen yet)
 * @param {string} category Category folder such as '01 Materials'
 * @param {string} current Value to keep selected (added when missing)
 * @returns {Promise<void>}
 */
async function loadSubfolderOptions(sel, code, category, current) {
  if (!sel) return;
  let names = [];
  if (code && category) {
    try {
      const res = await fetch(`/api/courses/${encodeURIComponent(code)}/subfolders?category=${encodeURIComponent(category)}`);
      if (res.ok) names = (await res.json()).subfolders || [];
    } catch (e) {
      console.warn('Could not list subfolders:', e);
    }
  }
  if (current && !names.includes(current)) names.unshift(current);
  sel.innerHTML = names.map(n => `<option value="${escHtml(n)}">${escHtml(n)}</option>`).join('') +
    `<option value="${PICK_NEW}">${_PICK_NEW_LABEL}</option>`;
  sel.value = current || names[0] || '';
  sel.dataset.prev = sel.value;
}

/**
 * Handle a subfolder <select> change: choosing「＋ 新增資料夾…」asks for a name and adds it.
 * @param {HTMLSelectElement} sel Changed select
 */
function onSubfolderPick(sel) {
  if (sel.value !== PICK_NEW) { sel.dataset.prev = sel.value; return; }
  const name = _askNewFolderName();
  if (!name) { sel.value = sel.dataset.prev || ''; return; }
  if (![...sel.options].some(o => o.value === name)) {
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = `${name}（新）`;
    sel.insertBefore(opt, sel.lastElementChild);
  }
  sel.value = name;
  sel.dataset.prev = name;
}

/**
 * In-page dialog asking the user to pick one option from a <select>.
 * @param {string} message Explanation shown above the list
 * @param {Array<{value: string, label: string}>} options Choices
 * @param {{okLabel?: string, allowNew?: boolean}} [opts] Button label; allowNew adds「＋ 新增資料夾…」
 * @returns {Promise<string|null>} Chosen value, or null when cancelled
 */
function askPick(message, options, { okLabel = '確定', allowNew = false } = {}) {
  return new Promise(resolve => {
    let overlay = document.getElementById('pickOverlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'pickOverlay';
      overlay.innerHTML = `<div id="pickBox" role="dialog" aria-modal="true"><div id="pickText"></div>
        <select id="pickSelect" class="input"></select>
        <div class="actions"><button id="pickCancel" class="btn btn-ghost">取消</button><button id="pickOk" class="btn btn-primary">確定</button></div></div>`;
      document.body.appendChild(overlay);
    }
    document.getElementById('pickText').textContent = message;
    const sel = document.getElementById('pickSelect');
    sel.innerHTML = options.map(o => `<option value="${escHtml(o.value)}">${escHtml(o.label)}</option>`).join('') +
      (allowNew ? `<option value="${PICK_NEW}">${_PICK_NEW_LABEL}</option>` : '');
    sel.dataset.prev = sel.value;
    sel.onchange = () => { if (allowNew) onSubfolderPick(sel); };
    const ok = document.getElementById('pickOk');
    ok.textContent = okLabel;
    const close = result => { overlay.style.display = 'none'; resolve(result); };
    ok.onclick = () => close(sel.value && sel.value !== PICK_NEW ? sel.value : null);
    document.getElementById('pickCancel').onclick = () => close(null);
    overlay.onclick = e => { if (e.target === overlay) close(null); };
    overlay.style.display = 'flex';
    sel.focus();
  });
}

/**
 * Refresh the literature toolbar's subfolder picker from the chosen course and category.
 * @returns {Promise<void>}
 */
async function refreshLitSubfolderPicker() {
  const sel = document.getElementById('litSubfolderInput');
  if (!sel) return;
  const code = document.getElementById('litCourseSelectWrap')?.getAttribute('data-value') || '';
  const category = document.getElementById('litCategorySelectWrap')?.getAttribute('data-value') || '01 Materials';
  await loadSubfolderOptions(sel, code, category, sel.value && sel.value !== PICK_NEW ? sel.value : 'Literature_Review');
}

/**
 * Fill an archive-menu subfolder picker (`select[data-lit-menu-sub]`) from its row's course and category.
 * @param {HTMLSelectElement} sel Row select
 * @returns {Promise<void>}
 */
async function refreshLitRowSubfolderPicker(sel) {
  const key = sel.getAttribute('data-lit-menu-sub');
  const scope = sel.parentElement || document;
  const code = scope.querySelector(`[data-lit-menu-course="${CSS.escape(key)}"]`)?.getAttribute('data-value') || '';
  const category = scope.querySelector(`[data-lit-menu-cat="${CSS.escape(key)}"]`)?.getAttribute('data-value') || '01 Materials';
  await loadSubfolderOptions(sel, code, category, sel.value && sel.value !== PICK_NEW ? sel.value : 'Literature_Review');
}

/**
 * Watch the literature course/category pickers and newly rendered archive menus, refreshing subfolder lists.
 */
function _watchLiteraturePickers() {
  const toolbar = ['litCourseSelectWrap', 'litCategorySelectWrap'].map(id => document.getElementById(id)).filter(Boolean);
  const attrObserver = new MutationObserver(() => refreshLitSubfolderPicker());
  toolbar.forEach(el => attrObserver.observe(el, { attributes: true, attributeFilter: ['data-value'] }));
  refreshLitSubfolderPicker();
  const rowObserver = new MutationObserver(records => {
    for (const r of records) {
      if (r.type === 'attributes') {
        const row = r.target.parentElement?.querySelector('select[data-lit-menu-sub]');
        if (row) refreshLitRowSubfolderPicker(row);
        continue;
      }
      r.addedNodes.forEach(node => {
        if (node.nodeType !== 1) return;
        node.querySelectorAll?.('select[data-lit-menu-sub]').forEach(sel => refreshLitRowSubfolderPicker(sel));
      });
    }
  });
  rowObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-value'] });
}

document.addEventListener('DOMContentLoaded', _watchLiteraturePickers);
