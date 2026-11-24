/**
 * Dedicated Literature Collection view (`#view-literature`) for SPEC-012.
 * Integrates APA/DOI parsing, Crossref/OpenAlex/OpenAthens PDF fetching,
 * interactive manual verification mode, inline collapse/expand PDF preview,
 * inline course archive menu, APA 7 export, and course import.
 */
(function () {
  'use strict';

  let litPollTimer = null;
  let cachedCourses = [];
  let visibleItemKeys = [];
  const selectedKeys = new Set();
  let expandedPdfKey = null;
  let expandedReviewKey = null;
  let openArchiveKey = null;
  let openColPop = null;
  let lastAllItems = [];
  let apaSearchQuery = '';
  const colFilters = { seq: null, status: null, target: null };
  let sortRules = [{ col: 'seq', dir: 'asc' }];
  const {
    litApi,
    escapeHtml,
    getSelectVal,
    setSelectVal,
    bindLitSelectMenu,
    getLitScale,
    mountInlinePdf,
    applyLitScale,
    renderExcelColPopoverHtml,
    caretSvg,
  } = window.LitUi;
  const { courseOptionsHtml, renderItemRow, sortItems, getColFilterVal, sortBadgeHtml } = window.LitRows;
  const { renderJobBanner, renderNotebookStatus, handleAddAndProcess, handleCopyApa, bindNotebookEvents } = window.LitActions;

  /**
   * Look up an element by its DOM id.
   * @param {string} id Element id.
   * @returns {HTMLElement|null} Matched element or null.
   */
  function litEl(id) {
    return document.getElementById(id);
  }

  /**
   * Populate the top custom course dropdown with registered courses.
   * @param {Array<object>} courses Course list from `/api/courses`.
   */
  function populateCourseDropdown(courses) {
    cachedCourses = courses || [];
    const menu = litEl('litCourseMenu');
    if (!menu) return;
    const prev = getSelectVal('litCourseSelectWrap');
    menu.innerHTML = courseOptionsHtml(cachedCourses, prev, '（不綁定 · 暫存 scratch）');
    setSelectVal('litCourseSelectWrap', prev);
  }

  /**
   * Update the "複製 APA 7 清單" button label and header select-all checkbox state.
   */
  function syncSelectionUi() {
    const btn = litEl('litCopyApaBtn');
    const allBox = litEl('litSelectAll');
    const n = selectedKeys.size;
    if (btn) btn.textContent = n > 0 ? `生成／複製已勾選 APA (${n})` : '複製 APA 7 清單';
    if (allBox && visibleItemKeys.length > 0) {
      allBox.checked = visibleItemKeys.every(k => selectedKeys.has(k));
    } else if (allBox) {
      allBox.checked = false;
    }
  }

  /**
   * Update multi-condition sort badges and Excel-style filter popovers on table headers.
   */
  function updateSortHeaders() {
    const labels = { seq: '序', status: '狀態', apa: 'APA 7th 格式名稱 / 操作', target: '歸檔位置' };
    document.querySelectorAll('#view-literature [data-lit-th]').forEach(wrap => {
      const col = wrap.getAttribute('data-lit-th');
      const isFiltered = col === 'apa' ? Boolean(apaSearchQuery.trim()) : Boolean(colFilters[col]);
      const badge = sortBadgeHtml(col, sortRules);
      const indicator = badge || caretSvg('down');
      const pop = openColPop === col
        ? renderExcelColPopoverHtml({ col, items: lastAllItems, sortRules, activeSet: colFilters[col], valGetter: getColFilterVal, apaQuery: apaSearchQuery })
        : '';
      wrap.innerHTML = `<button type="button" class="lit-th-btn${isFiltered ? ' filtered' : ''}" data-lit-excel="${col}"><span>${escapeHtml(labels[col] || col)}</span>${indicator}</button>${pop}`;
    });
  }

  /**
   * Apply top filter + Excel column filters to `lastAllItems` and render the table.
   * @param {boolean} [skipHeaderUpdate] When true, keep open popover DOM intact (for live typing).
   */
  function applyAllFiltersAndRender(skipHeaderUpdate) {
    const mode = getSelectVal('litFilterSelectWrap') || 'all';
    const q = apaSearchQuery.trim().toLowerCase();
    const visible = lastAllItems.filter(item => {
      if (mode === 'unarchived' && item.imported_to_course) return false;
      if (mode === 'archived' && !item.imported_to_course) return false;
      if (colFilters.seq && !colFilters.seq.has(getColFilterVal(item, 'seq'))) return false;
      if (colFilters.status && !colFilters.status.has(getColFilterVal(item, 'status'))) return false;
      if (colFilters.target && !colFilters.target.has(getColFilterVal(item, 'target'))) return false;
      if (q && !`${item.apa || ''} ${item.input || ''} ${item.title || ''} ${item.key || ''}`.toLowerCase().includes(q)) return false;
      return true;
    });
    renderItems(visible, skipHeaderUpdate);
  }

  /**
   * Render the full list of literature items into `#litItemsBody`.
   * @param {Array<object>} items Literature items array.
   * @param {boolean} [skipHeaderUpdate] When true, avoid rebuilding `thead` popovers.
   */
  function renderItems(items, skipHeaderUpdate) {
    const body = litEl('litItemsBody');
    if (!body) return;
    const sorted = sortItems(items || [], sortRules);
    visibleItemKeys = sorted.map(i => i.key);
    syncSelectionUi();
    if (!skipHeaderUpdate) updateSortHeaders();
    if (!sorted.length) {
      body.innerHTML = '<tr><td colspan="4" class="muted small">尚無文獻紀錄。請在上方貼上 APA、標題或 DOI。</td></tr>';
      return;
    }
    const st = { selectedKeys, expandedPdfKey, expandedReviewKey, openArchiveKey, courses: cachedCourses };
    body.innerHTML = sorted.map(item => renderItemRow(item, st)).join('');
    const expandEl = litEl('litExpandPages');
    if (expandEl) {
      const pdfUrl = expandEl.getAttribute('data-pdf-url');
      if (pdfUrl) mountInlinePdf(pdfUrl).catch(console.error);
    }
  }

  /**
   * Refresh the literature list, course dropdown, and background job polling.
   * @returns {Promise<void>}
   */
  async function refreshLiterature() {
    const [litData, coursesData, nbData] = await Promise.all([
      litApi('/api/literature'),
      litApi('/api/courses').catch(() => ({ courses: [] })),
      litApi('/api/literature/notebook').catch(() => null),
    ]);
    populateCourseDropdown(coursesData.courses || coursesData || []);
    const dirEl = litEl('litUnarchivedDir');
    if (dirEl && litData.unarchived_dir) dirEl.textContent = litData.unarchived_dir;
    if (nbData) renderNotebookStatus(nbData);
    renderJobBanner(litData);

    lastAllItems = (litData.items || []).map((item, idx) => ({ ...item, _seq: idx + 1 }));
    applyAllFiltersAndRender();

    const anyRunning = Boolean(litData.running || nbData?.review_running);
    if (anyRunning && !litPollTimer) {
      litPollTimer = setInterval(refreshLiterature, 2500);
    } else if (!anyRunning && litPollTimer) {
      clearInterval(litPollTimer);
      litPollTimer = null;
    }
  }

  /**
   * Submit the inline archive menu selection for a given item key.
   * @param {string} key Literature item key.
   * @returns {Promise<void>}
   */
  async function submitInlineArchive(key) {
    const body = litEl('litItemsBody');
    const courseSel = body?.querySelector(`[data-lit-menu-course="${CSS.escape(key)}"]`);
    const catSel = body?.querySelector(`[data-lit-menu-cat="${CSS.escape(key)}"]`);
    const subInput = body?.querySelector(`[data-lit-menu-sub="${CSS.escape(key)}"]`);
    const courseCode = courseSel?.getAttribute('data-value') || '';
    if (!courseCode) {
      alert('請選擇要歸檔的課程！');
      return;
    }
    await litApi(`/api/literature/${encodeURIComponent(key)}/import-to-course`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        course_code: courseCode,
        category: catSel?.getAttribute('data-value') || '01 Materials',
        subfolder: subInput?.value?.trim() || 'Literature_Review',
      }),
    });
    openArchiveKey = null;
  }

  /**
   * Handle review expand/generate/regenerate clicks on a literature row.
   * @param {HTMLElement} target Clicked element.
   * @returns {Promise<boolean>} True if handled.
   */
  async function handleReviewAction(target) {
    const revBtn = target.closest('[data-lit-review]');
    const revKey = revBtn ? revBtn.getAttribute('data-lit-review') : null;
    if (revKey) {
      expandedPdfKey = null;
      if (expandedReviewKey === revKey) {
        expandedReviewKey = null;
      } else {
        if (revBtn.textContent.includes('生成')) {
          revBtn.textContent = '生成中…';
          await litApi(`/api/literature/${encodeURIComponent(revKey)}/review`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ force: false }),
          });
        }
        expandedReviewKey = revKey;
      }
      await refreshLiterature();
      return true;
    }
    const regenKey = target.getAttribute('data-lit-review-regen');
    if (regenKey) {
      target.textContent = '重新生成中…';
      await litApi(`/api/literature/${encodeURIComponent(regenKey)}/review`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ force: true }),
      });
      expandedReviewKey = regenKey;
      await refreshLiterature();
      return true;
    }
    return false;
  }

  /**
   * Handle row action button clicks (collapse/expand PDF, review, archive menu, retry, reidentify, delete).
   * @param {MouseEvent} ev Click event from `#litItemsBody`.
   * @returns {Promise<void>}
   */
  async function handleRowAction(ev) {
    const target = ev.target;
    if (!(target instanceof HTMLElement)) return;
    if (await handleReviewAction(target)) return;

    const zoomBtn = target.closest('[data-lit-zoom]');
    if (zoomBtn) { applyLitScale(getLitScale() + Number(zoomBtn.getAttribute('data-lit-zoom'))); return; }
    if (target.closest('[data-lit-zoom-cycle]')) {
      const s = getLitScale();
      applyLitScale(s < 1.30 ? 1.35 : (s < 1.70 ? 1.75 : 1.0));
      return;
    }
    const viewBtn = target.closest('[data-lit-view]');
    if (viewBtn) {
      const k = viewBtn.getAttribute('data-lit-view');
      expandedReviewKey = null;
      expandedPdfKey = expandedPdfKey === k ? null : k;
      return refreshLiterature();
    }
    const toggleArch = target.getAttribute('data-lit-toggle-archive');
    if (toggleArch) { openArchiveKey = openArchiveKey === toggleArch ? null : toggleArch; return refreshLiterature(); }
    if (target.hasAttribute('data-lit-cancel-archive')) { openArchiveKey = null; return refreshLiterature(); }
    const confirmArch = target.getAttribute('data-lit-confirm-archive');
    if (confirmArch) { await submitInlineArchive(confirmArch); return refreshLiterature(); }
    return handleStatusAction(target);
  }

  /**
   * Handle status-changing row actions (unarchive, refresh, retry, reidentify, delete).
   * @param {HTMLElement} target Clicked button element.
   * @returns {Promise<void>}
   */
  async function handleStatusAction(target) {
    const unarchiveKey = target.getAttribute('data-lit-unarchive');
    if (unarchiveKey) {
      await litApi(`/api/literature/${encodeURIComponent(unarchiveKey)}/unarchive`, { method: 'POST' });
      return refreshLiterature();
    }
    const refreshKey = target.getAttribute('data-lit-refresh');
    if (refreshKey) {
      await litApi(`/api/literature/${encodeURIComponent(refreshKey)}/refresh`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interactive: Boolean(litEl('litInteractiveCheck')?.checked) }),
      });
      return refreshLiterature();
    }
    const retryKey = target.getAttribute('data-lit-retry');
    if (retryKey) {
      await litApi(`/api/literature/${encodeURIComponent(retryKey)}/retry`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ interactive: Boolean(litEl('litInteractiveCheck')?.checked) }),
      });
      return refreshLiterature();
    }
    const reidKey = target.getAttribute('data-lit-reid');
    if (reidKey) {
      const text = prompt('請輸入修正後的 APA、標題或 DOI：');
      if (!text || !text.trim()) return;
      await litApi(`/api/literature/${encodeURIComponent(reidKey)}/reidentify`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text.trim() }),
      });
      return refreshLiterature();
    }
    const delKey = target.getAttribute('data-lit-del');
    if (delKey) {
      if (!confirm(`確定要從清單移除「${delKey}」嗎？（磁碟上的 PDF 檔案會保留）`)) return;
      await litApi(`/api/literature/${encodeURIComponent(delKey)}`, { method: 'DELETE' });
      return refreshLiterature();
    }
  }

  /**
   * Update `sortRules` for a column, optionally forcing `asc`, `desc`, or `none`.
   * @param {string} col Column key.
   * @param {string} [mode] Optional explicit direction (`asc` | `desc` | `none`).
   */
  function updateSortRule(col, mode) {
    const idx = sortRules.findIndex(r => r.col === col);
    if (mode === 'none') {
      if (idx !== -1) sortRules.splice(idx, 1);
    } else if (mode === 'asc' || mode === 'desc') {
      if (idx === -1) sortRules.push({ col, dir: mode });
      else sortRules[idx].dir = mode;
    } else if (idx === -1) {
      sortRules.push({ col, dir: 'asc' });
    } else if (sortRules[idx].dir === 'asc') {
      sortRules[idx].dir = 'desc';
    } else {
      sortRules.splice(idx, 1);
    }
    if (!sortRules.length) sortRules = [{ col: 'seq', dir: 'asc' }];
  }

  /**
   * Handle click events inside `#view-literature thead` (direct sort, Excel popover toggle, popover sort).
   * @param {MouseEvent} ev Click event.
   */
  function handleTheadClick(ev) {
    const t = ev.target instanceof Element ? ev.target : null;
    if (!t) return;
    const popSort = t.closest('[data-lit-col-sort]');
    if (popSort) {
      ev.stopPropagation();
      const [col, dir] = (popSort.getAttribute('data-lit-col-sort') || '').split(':');
      updateSortRule(col, dir);
      openColPop = null;
      return applyAllFiltersAndRender();
    }
    if (t.closest('[data-lit-clear-search]')) {
      ev.stopPropagation();
      apaSearchQuery = '';
      return applyAllFiltersAndRender();
    }
    const excelBtn = t.closest('[data-lit-excel]');
    if (excelBtn) {
      ev.stopPropagation();
      const col = excelBtn.getAttribute('data-lit-excel');
      openColPop = openColPop === col ? null : col;
      updateSortHeaders();
      if (openColPop === 'apa') document.querySelector('[data-lit-col-search="apa"]')?.focus();
      return;
    }
    if (t.closest('.lit-col-pop')) {
      ev.stopPropagation();
    }
  }

  /**
   * Handle live keyword typing inside the `APA 7th` column filter input.
   * @param {Event} ev Input event.
   */
  function handleTheadInput(ev) {
    const t = ev.target instanceof HTMLInputElement ? ev.target : null;
    if (!t || !t.hasAttribute('data-lit-col-search')) return;
    apaSearchQuery = t.value || '';
    const btn = document.querySelector('#view-literature [data-lit-excel="apa"]');
    if (btn) btn.classList.toggle('filtered', Boolean(apaSearchQuery.trim()));
    applyAllFiltersAndRender(true);
  }

  /**
   * Handle checkbox changes inside Excel column filter popovers.
   * @param {Event} ev Change event.
   */
  function handleTheadChange(ev) {
    const t = ev.target instanceof HTMLInputElement ? ev.target : null;
    if (!t) return;
    const allCol = t.getAttribute('data-lit-col-all');
    if (allCol) {
      colFilters[allCol] = t.checked ? null : new Set();
      return applyAllFiltersAndRender();
    }
    const col = t.getAttribute('data-lit-col');
    if (!col) return;
    const boxes = Array.from(document.querySelectorAll(`#view-literature thead input[data-lit-col="${col}"]`));
    const checked = boxes.filter(b => b.checked).map(b => b.getAttribute('data-lit-col-val') || '');
    colFilters[col] = checked.length === boxes.length ? null : new Set(checked);
    applyAllFiltersAndRender();
  }

  /**
   * Bind multi-column sort headers, custom `.lit-select` menus, and global close listeners.
   */
  function bindFilterAndSelectEvents() {
    const thead = document.querySelector('#view-literature thead');
    thead?.addEventListener('click', handleTheadClick);
    thead?.addEventListener('input', handleTheadInput);
    thead?.addEventListener('change', handleTheadChange);
    bindLitSelectMenu('view-literature', wrapId => {
      if (wrapId === 'litFilterSelectWrap') applyAllFiltersAndRender();
    });
    document.addEventListener('click', ev => {
      const t = ev.target;
      if (t instanceof Element && !t.closest('.lit-select')) {
        document.querySelectorAll('#view-literature .lit-select.open').forEach(s => s.classList.remove('open'));
      }
      if (openColPop && t instanceof Element && !t.closest('.lit-th-wrap')) {
        openColPop = null;
        updateSortHeaders();
      }
      if (!openArchiveKey) return;
      if (t instanceof Element && (t.closest('.lit-archive-menu') || t.closest('[data-lit-toggle-archive]'))) return;
      openArchiveKey = null;
      refreshLiterature();
    });
    document.addEventListener('keydown', ev => {
      if (ev.key !== 'Escape') return;
      document.querySelectorAll('#view-literature .lit-select.open').forEach(s => s.classList.remove('open'));
      if (openColPop) { openColPop = null; updateSortHeaders(); }
      if (openArchiveKey) { openArchiveKey = null; refreshLiterature(); }
    });
  }

  /**
   * Bind DOM event handlers for the Literature Collection view.
   */
  function bindLiteratureEvents() {
    bindNotebookEvents(refreshLiterature);
    bindFilterAndSelectEvents();
    litEl('litStartBtn')?.addEventListener('click', () => handleAddAndProcess(false, refreshLiterature).catch(e => alert(e.message)));
    litEl('litIdentifyBtn')?.addEventListener('click', () => handleAddAndProcess(true, refreshLiterature).catch(e => alert(e.message)));
    litEl('litLookupMissingBtn')?.addEventListener('click', async () => {
      await litApi('/api/literature/process', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identify_only: true, no_browser: true }),
      });
      await refreshLiterature();
    });
    litEl('litCopyApaBtn')?.addEventListener('click', () => handleCopyApa(selectedKeys).catch(e => alert(e.message)));
    litEl('litReportBtn')?.addEventListener('click', () => window.open('/api/literature/export/report', '_blank'));
    litEl('litSelectAll')?.addEventListener('change', ev => {
      const checked = Boolean(ev.target?.checked);
      visibleItemKeys.forEach(k => (checked ? selectedKeys.add(k) : selectedKeys.delete(k)));
      document.querySelectorAll('.lit-row-check').forEach(el => { el.checked = checked; });
      syncSelectionUi();
    });
    litEl('litApaPreviewClose')?.addEventListener('click', () => {
      const box = litEl('litApaPreviewBox');
      if (box) box.style.display = 'none';
    });
    litEl('litItemsBody')?.addEventListener('change', ev => {
      const t = ev.target;
      if (!(t instanceof HTMLInputElement)) return;
      const key = t.getAttribute('data-lit-select');
      if (!key) return;
      if (t.checked) selectedKeys.add(key); else selectedKeys.delete(key);
      syncSelectionUi();
    });
    litEl('litItemsBody')?.addEventListener('click', ev => handleRowAction(ev).catch(e => alert(e.message)));
  }

  /**
   * Public hook invoked by `studio-nav.js` when switching to the literature tab.
   */
  window.loadLiteratureView = function () {
    refreshLiterature().catch(console.error);
  };

  document.addEventListener('DOMContentLoaded', bindLiteratureEvents);
})();
