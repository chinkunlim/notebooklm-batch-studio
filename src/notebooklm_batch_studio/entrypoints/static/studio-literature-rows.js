/**
 * Row rendering, archive menu, and sort/filter helpers for the Literature Collection table (SPEC-012).
 * Split out of studio-literature.js; functions are pure and take the view state they need as
 * arguments. Every untrusted value is escaped with LitUi.escapeHtml (Refs: ISSUE-046).
 */
(function () {
  'use strict';

  const { statusBadgeClass, shortStatusLabel, escapeHtml, getSelectVal, renderExpandRowHtml, caretSvg } = window.LitUi;
  const CATEGORIES = ['01 Materials', '02 Handouts', '03 Notes', '04 Homework', '05 Assignments'];
  /**
   * Return configured study categories when loaded from `/api/study/layout`.
   * @returns {Array<string>} Category names
   */
  function getCategories() {
    return Array.isArray(window.STUDY_CATEGORIES) && window.STUDY_CATEGORIES.length ? window.STUDY_CATEGORIES : CATEGORIES;
  }

  /**
   * Build custom `.lit-select-opt` buttons for the available courses.
   * @param {Array<object>} courses Cached course list.
   * @param {string} selectedCode Currently selected course code.
   * @param {string} emptyLabel Label for the empty option.
   * @returns {string} HTML options string.
   */
  function courseOptionsHtml(courses, selectedCode, emptyLabel) {
    const base = `<button type="button" class="lit-select-opt${selectedCode ? '' : ' on'}" data-val="">${escapeHtml(emptyLabel)}</button>`;
    return base + courses.map(c => {
      const prefix = c.term ? `[${c.term}] ` : '';
      const on = c.code === selectedCode ? ' on' : '';
      return `<button type="button" class="lit-select-opt${on}" data-val="${escapeHtml(c.code)}">${escapeHtml(prefix + c.name + ' (' + c.code + ')')}</button>`;
    }).join('');
  }

  /**
   * Render the inline archive popover menu inside the `歸檔位置` cell when open.
   * @param {object} item Serialized literature item.
   * @param {object} st View state (`openArchiveKey`, `courses`).
   * @returns {string} HTML markup for the archive menu, or empty string.
   */
  function renderArchiveMenu(item, st) {
    if (st.openArchiveKey !== item.key) return '';
    const defCourse = item.course_code || getSelectVal('litCourseSelectWrap') || '';
    const defCat = item.target_category || getSelectVal('litCategorySelectWrap') || '01 Materials';
    const defSub = item.target_subfolder || document.getElementById('litSubfolderInput')?.value || 'Literature_Review';
    const courseObj = st.courses.find(c => c.code === defCourse);
    const courseLabel = courseObj ? `${courseObj.term ? `[${courseObj.term}] ` : ''}${courseObj.name} (${courseObj.code})` : '請選擇科目…';
    const catOpts = getCategories().map(c => `<button type="button" class="lit-select-opt${c === defCat ? ' on' : ''}" data-val="${escapeHtml(c)}">${escapeHtml(c)}</button>`).join('');
    const key = escapeHtml(item.key);
    return `
      <div class="lit-archive-menu">
        <div class="lit-select" data-lit-menu-course="${key}" data-value="${escapeHtml(defCourse)}">
          <button type="button" class="lit-select-btn"><span class="lit-sel-txt">${escapeHtml(courseLabel)}</span><i class="icon-chevron-down"></i></button>
          <div class="lit-select-menu">${courseOptionsHtml(st.courses, defCourse, '請選擇科目…')}</div>
        </div>
        <div class="lit-select" data-lit-menu-cat="${key}" data-value="${escapeHtml(defCat)}">
          <button type="button" class="lit-select-btn"><span class="lit-sel-txt">${escapeHtml(defCat)}</span><i class="icon-chevron-down"></i></button>
          <div class="lit-select-menu">${catOpts}</div>
        </div>
        <select class="input" data-lit-menu-sub="${key}" onchange="onSubfolderPick(this)" aria-label="歸檔資料夾"><option value="${escapeHtml(defSub)}">${escapeHtml(defSub)}</option></select>
        <div style="display:flex;gap:6px">
          <button class="btn btn-xs btn-primary" data-lit-confirm-archive="${key}">確認歸檔</button>
          <button class="btn btn-xs btn-soft" data-lit-cancel-archive="${key}">取消</button>
        </div>
      </div>`;
  }

  /**
   * Render the right-hand `歸檔位置` cell with inline archive/re-archive controls.
   * @param {object} item Serialized literature item.
   * @param {object} st View state (`openArchiveKey`, `courses`).
   * @returns {string} HTML `<td>` content.
   */
  function renderTargetCell(item, st) {
    const label = item.course_code
      ? `${escapeHtml(item.course_code)} → ${escapeHtml(item.target_category)}/${escapeHtml(item.target_subfolder)}`
      : '未歸檔（暫存區）';
    const key = escapeHtml(item.key);
    let btns = '';
    if (item.file) {
      btns = item.imported_to_course
        ? `<button class="btn btn-xs btn-soft" data-lit-toggle-archive="${key}">改歸檔</button>
           <button class="btn btn-xs btn-soft" data-lit-unarchive="${key}">退回未歸檔</button>`
        : `<button class="btn btn-xs btn-primary" data-lit-toggle-archive="${key}">歸檔到課程</button>`;
    }
    return `
      <div class="lit-target-wrap">
        <div class="small muted">${label}</div>
        <div class="lit-target-actions">${btns}</div>
        ${renderArchiveMenu(item, st)}
      </div>`;
  }

  /**
   * Render the action buttons (PDF, Review, refresh, retry, re-identify, delete) of one row.
   * @param {object} item Serialized literature item.
   * @param {object} st View state (`expandedPdfKey`, `expandedReviewKey`).
   * @returns {string} HTML for the `.lit-actions` box.
   */
  function renderRowActions(item, st) {
    const key = escapeHtml(item.key);
    const isOpen = st.expandedPdfKey === item.key;
    const isRevOpen = st.expandedReviewKey === item.key;
    const pdfBtn = item.file_url
      ? `<button class="btn btn-xs ${isOpen ? 'btn-primary' : 'btn-soft'}" data-lit-view="${key}">${isOpen ? '收合 PDF' : '查看 PDF'}</button>`
      : '';
    const reviewLabel = item.has_review ? (isRevOpen ? '收合 Review' : '查看 Review') : '生成 Review';
    const reviewBtn = item.file
      ? `<button class="btn btn-xs ${isRevOpen ? 'btn-primary' : 'btn-soft'}" data-lit-review="${key}">${reviewLabel}</button>`
      : '';
    const refreshBtn = item.status === 'downloaded_copy'
      ? `<button class="btn btn-xs btn-soft" data-lit-refresh="${key}" title="嘗試從出版社下載正式版，找不到時保留原檔">試抓正式版</button>`
      : '';
    return `<div class="lit-actions">${pdfBtn}${reviewBtn}${refreshBtn}
            <button class="btn btn-xs btn-soft" data-lit-retry="${key}">重試</button>
            <button class="btn btn-xs btn-soft" data-lit-reid="${key}">改字重認</button>
            <button class="btn btn-xs btn-soft" data-lit-del="${key}">刪除</button></div>`;
  }

  /**
   * Render one table row (plus optional expanded PDF / Review row) for a tracked literature item.
   * @param {object} item Serialized literature item.
   * @param {object} st View state (`selectedKeys`, `expandedPdfKey`, `expandedReviewKey`, `openArchiveKey`, `courses`).
   * @returns {string} HTML `<tr>` markup.
   */
  function renderItemRow(item, st) {
    const checked = st.selectedKeys.has(item.key) ? ' checked' : '';
    const stageText = item.stage ? `<div class="small muted" style="margin-top:4px">目前步驟：${escapeHtml(item.stage)}</div>` : '';
    const notesText = item.notes ? `<div class="small muted" style="margin-top:4px">${escapeHtml(item.notes)}</div>` : '';
    return `
      <tr class="lit-row">
        <td class="lit-col-seq">
          <label class="lit-check-cell">
            <input type="checkbox" class="lit-row-check" data-lit-select="${escapeHtml(item.key)}"${checked} />
            <span class="small muted">${escapeHtml(item._seq)}</span>
          </label>
        </td>
        <td class="lit-col-status">
          <span class="${statusBadgeClass(item.status)}" title="${escapeHtml(item.source || '')}">${escapeHtml(shortStatusLabel(item))}</span>
        </td>
        <td class="lit-col-main">
          <div class="lit-apa-box">${item.apa_html || escapeHtml(item.apa || item.input)}</div>
          ${stageText}${notesText}${renderRowActions(item, st)}
        </td>
        <td class="lit-col-target">${renderTargetCell(item, st)}</td>
      </tr>${renderExpandRowHtml(item, st.expandedPdfKey, st.expandedReviewKey)}`;
  }

  /**
   * Compare two items by one column key.
   * @param {object} a First item.
   * @param {object} b Second item.
   * @param {string} col Column key (`seq` | `status` | `apa` | `target`).
   * @returns {number} Comparison result.
   */
  function compareByCol(a, b, col) {
    if (col === 'seq') return a._seq - b._seq;
    if (col === 'status') return String(a.status_label || a.status).localeCompare(String(b.status_label || b.status), 'zh-Hant');
    if (col === 'target') return String(a.course_code || '').localeCompare(String(b.course_code || ''), 'zh-Hant');
    return String(a.apa || a.input || '').localeCompare(String(b.apa || b.input || ''), 'en');
  }

  /**
   * Sort visible literature items using multi-condition sort rules.
   * @param {Array<object>} items Literature items with `_seq` assigned.
   * @param {Array<object>} sortRules Ordered `{col, dir}` rules.
   * @returns {Array<object>} Sorted copy.
   */
  function sortItems(items, sortRules) {
    return [...items].sort((a, b) => {
      for (const rule of sortRules) {
        const cmp = compareByCol(a, b, rule.col);
        if (cmp !== 0) return cmp * (rule.dir === 'asc' ? 1 : -1);
      }
      return a._seq - b._seq;
    });
  }

  /**
   * Extract the display/filter key for a filterable table column.
   * @param {object} item Serialized literature item.
   * @param {string} col Column key (`seq` | `status` | `target`).
   * @returns {string} Display label used in column checkboxes.
   */
  function getColFilterVal(item, col) {
    if (col === 'seq') return String(item._seq);
    if (col === 'status') return shortStatusLabel(item);
    return item.course_code ? `${item.course_code} → ${item.target_category}/${item.target_subfolder}` : '未歸檔（暫存區）';
  }

  /**
   * Format the sort indicator badge HTML for a column key.
   * @param {string} col Column key.
   * @param {Array<object>} sortRules Ordered `{col, dir}` rules.
   * @returns {string} Badge HTML or empty string.
   */
  function sortBadgeHtml(col, sortRules) {
    const idx = sortRules.findIndex(r => r.col === col);
    if (idx === -1) return '';
    const arrow = caretSvg(sortRules[idx].dir === 'asc' ? 'up' : 'down');
    const num = sortRules.length > 1 ? `${idx + 1}` : '';
    return `<span class="lit-sort-badge">${num}${arrow}</span>`;
  }

  window.LitRows = { courseOptionsHtml, renderItemRow, sortItems, getColFilterVal, sortBadgeHtml };
})();
