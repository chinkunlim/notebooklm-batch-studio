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
    statusBadgeClass,
    shortStatusLabel,
    escapeHtml,
    getSelectVal,
    setSelectVal,
    bindLitSelectMenu,
    getLitScale,
    mountInlinePdf,
    applyLitScale,
    renderExpandRowHtml,
    renderExcelColPopoverHtml,
    caretSvg,
  } = window.LitUi;

  /**
   * Look up an element by its DOM id.
   * @param {string} id Element id.
   * @returns {HTMLElement|null} Matched element or null.
   */
  function litEl(id) {
    return document.getElementById(id);
  }

  /**
   * Build custom `.lit-select-opt` buttons for the available courses.
   * @param {string} selectedCode Currently selected course code.
   * @param {string} emptyLabel Label for the empty option.
   * @returns {string} HTML options string.
   */
  function courseOptionsHtml(selectedCode, emptyLabel) {
    const base = `<button type="button" class="lit-select-opt${selectedCode ? '' : ' on'}" data-val="">${escapeHtml(emptyLabel)}</button>`;
    return base + cachedCourses.map(c => {
      const prefix = c.term ? `[${c.term}] ` : '';
      const on = c.code === selectedCode ? ' on' : '';
      return `<button type="button" class="lit-select-opt${on}" data-val="${escapeHtml(c.code)}">${escapeHtml(prefix + c.name + ' (' + c.code + ')')}</button>`;
    }).join('');
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
    menu.innerHTML = courseOptionsHtml(prev, '（不綁定 · 暫存 scratch）');
    setSelectVal('litCourseSelectWrap', prev);
  }

  /**
   * Render the active or latest literature job status banner.
   * @param {object} data Response payload from `/api/literature`.
   */
  function renderJobBanner(data) {
    const banner = litEl('litJobBanner');
    if (!banner) return;
    const job = data.job;
    if (data.running && job) {
      banner.style.display = 'flex';
      banner.innerHTML = `<span>處理中 (${job.done || 0}/${job.total || 0})：${escapeHtml(job.message || '')}</span>`;
      return;
    }
    if (job && job.message) {
      banner.style.display = 'flex';
      banner.innerHTML = `<span>最近執行：${escapeHtml(job.message)}</span>`;
      return;
    }
    banner.style.display = 'none';
  }

  /**
   * Render the inline archive popover menu inside the `歸檔位置` cell when open.
   * @param {object} item Serialized literature item.
   * @returns {string} HTML markup for the archive menu, or empty string.
   */
  function renderArchiveMenu(item) {
    if (openArchiveKey !== item.key) return '';
    const defCourse = item.course_code || getSelectVal('litCourseSelectWrap') || '';
    const defCat = item.target_category || getSelectVal('litCategorySelectWrap') || '01 Material';
    const defSub = item.target_subfolder || litEl('litSubfolderInput')?.value || 'Literature_Review';
    const courseObj = cachedCourses.find(c => c.code === defCourse);
    const courseLabel = courseObj ? `${courseObj.term ? `[${courseObj.term}] ` : ''}${courseObj.name} (${courseObj.code})` : '請選擇科目…';
    const cats = ['01 Material', '02 Handout', '03 Notes', '04 Homework', '05 Assignments'];
    const catOpts = cats.map(c => `<button type="button" class="lit-select-opt${c === defCat ? ' on' : ''}" data-val="${c}">${c}</button>`).join('');
    return `
      <div class="lit-archive-menu">
        <div class="lit-select" data-lit-menu-course="${escapeHtml(item.key)}" data-value="${escapeHtml(defCourse)}">
          <button type="button" class="lit-select-btn"><span class="lit-sel-txt">${escapeHtml(courseLabel)}</span><i class="icon-chevron-down"></i></button>
          <div class="lit-select-menu">${courseOptionsHtml(defCourse, '請選擇科目…')}</div>
        </div>
        <div class="lit-select" data-lit-menu-cat="${escapeHtml(item.key)}" data-value="${escapeHtml(defCat)}">
          <button type="button" class="lit-select-btn"><span class="lit-sel-txt">${escapeHtml(defCat)}</span><i class="icon-chevron-down"></i></button>
          <div class="lit-select-menu">${catOpts}</div>
        </div>
        <input class="input" type="text" value="${escapeHtml(defSub)}" data-lit-menu-sub="${escapeHtml(item.key)}" placeholder="子資料夾" />
        <div style="display:flex;gap:6px">
          <button class="btn btn-xs btn-primary" data-lit-confirm-archive="${escapeHtml(item.key)}">確認歸檔</button>
          <button class="btn btn-xs btn-soft" data-lit-cancel-archive="${escapeHtml(item.key)}">取消</button>
        </div>
      </div>`;
  }

  /**
   * Render the right-hand `歸檔位置` cell with inline archive/re-archive controls.
   * @param {object} item Serialized literature item.
   * @returns {string} HTML `<td>` content.
   */
  function renderTargetCell(item) {
    const label = item.course_code
      ? `${escapeHtml(item.course_code)} → ${escapeHtml(item.target_category)}/${escapeHtml(item.target_subfolder)}`
      : '未歸檔（暫存區）';
    let btns = '';
    if (item.file) {
      btns = item.imported_to_course
        ? `<button class="btn btn-xs btn-soft" data-lit-toggle-archive="${escapeHtml(item.key)}">改歸檔</button>
           <button class="btn btn-xs btn-soft" data-lit-unarchive="${escapeHtml(item.key)}">退回未歸檔</button>`
        : `<button class="btn btn-xs btn-primary" data-lit-toggle-archive="${escapeHtml(item.key)}">歸檔到課程</button>`;
    }
    return `
      <div class="lit-target-wrap">
        <div class="small muted">${label}</div>
        <div class="lit-target-actions">${btns}</div>
        ${renderArchiveMenu(item)}
      </div>`;
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
   * Render one table row (plus optional expanded PDF row) for a tracked literature item.
   * @param {object} item Serialized literature item.
   * @returns {string} HTML `<tr>` markup.
   */
  function renderItemRow(item) {
    const isOpen = expandedPdfKey === item.key;
    const checked = selectedKeys.has(item.key) ? ' checked' : '';
    const pdfBtn = item.file_url
      ? `<button class="btn btn-xs ${isOpen ? 'btn-primary' : 'btn-soft'}" data-lit-view="${escapeHtml(item.key)}">${isOpen ? '收合 PDF' : '查看 PDF'}</button>`
      : '';
    const refreshBtn = item.status === 'downloaded_copy'
      ? `<button class="btn btn-xs btn-soft" data-lit-refresh="${escapeHtml(item.key)}" title="嘗試從出版社下載正式版，找不到時保留原檔">試抓正式版</button>`
      : '';
    const isRevOpen = expandedReviewKey === item.key;
    const reviewBtn = item.file
      ? `<button class="btn btn-xs ${isRevOpen ? 'btn-primary' : 'btn-soft'}" data-lit-review="${escapeHtml(item.key)}">${item.has_review ? (isRevOpen ? '收合 Review' : '查看 Review') : '生成 Review'}</button>`
      : '';
    const stageText = item.stage ? `<div class="small muted" style="margin-top:4px">目前步驟：${escapeHtml(item.stage)}</div>` : '';
    const notesText = item.notes ? `<div class="small muted" style="margin-top:4px">${escapeHtml(item.notes)}</div>` : '';
    return `
      <tr class="lit-row">
        <td class="lit-col-seq">
          <label class="lit-check-cell">
            <input type="checkbox" class="lit-row-check" data-lit-select="${escapeHtml(item.key)}"${checked} />
            <span class="small muted">${item._seq}</span>
          </label>
        </td>
        <td class="lit-col-status">
          <span class="${statusBadgeClass(item.status)}" title="${escapeHtml(item.source || '')}">${escapeHtml(shortStatusLabel(item))}</span>
        </td>
        <td class="lit-col-main">
          <div class="lit-apa-box">${item.apa_html || escapeHtml(item.apa || item.input)}</div>
          ${stageText}
          ${notesText}
          <div class="lit-actions">
            ${pdfBtn}
            ${reviewBtn}
            ${refreshBtn}
            <button class="btn btn-xs btn-soft" data-lit-retry="${escapeHtml(item.key)}">重試</button>
            <button class="btn btn-xs btn-soft" data-lit-reid="${escapeHtml(item.key)}">改字重認</button>
            <button class="btn btn-xs btn-soft" data-lit-del="${escapeHtml(item.key)}">刪除</button>
          </div>
        </td>
        <td class="lit-col-target">${renderTargetCell(item)}</td>
      </tr>${renderExpandRowHtml(item, expandedPdfKey, expandedReviewKey)}`;
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
   * Sort visible literature items using multi-condition `sortRules`.
   * @param {Array<object>} items Literature items with `_seq` assigned.
   * @returns {Array<object>} Sorted copy.
   */
  function sortItems(items) {
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
   * @returns {string} Badge HTML or empty string.
   */
  function sortBadgeHtml(col) {
    const idx = sortRules.findIndex(r => r.col === col);
    if (idx === -1) return '';
    const arrow = caretSvg(sortRules[idx].dir === 'asc' ? 'up' : 'down');
    const num = sortRules.length > 1 ? `${idx + 1}` : '';
    return `<span class="lit-sort-badge">${num}${arrow}</span>`;
  }

  /**
   * Update multi-condition sort badges and Excel-style filter popovers on table headers.
   */
  function updateSortHeaders() {
    const labels = { seq: '序', status: '狀態', apa: 'APA 7th 格式名稱 / 操作', target: '歸檔位置' };
    document.querySelectorAll('#view-literature [data-lit-th]').forEach(wrap => {
      const col = wrap.getAttribute('data-lit-th');
      const isFiltered = col === 'apa' ? Boolean(apaSearchQuery.trim()) : Boolean(colFilters[col]);
      const badge = sortBadgeHtml(col);
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
    const sorted = sortItems(items || []);
    visibleItemKeys = sorted.map(i => i.key);
    syncSelectionUi();
    if (!skipHeaderUpdate) updateSortHeaders();
    if (!sorted.length) {
      body.innerHTML = '<tr><td colspan="4" class="muted small">尚無文獻紀錄。請在上方貼上 APA、標題或 DOI。</td></tr>';
      return;
    }
    body.innerHTML = sorted.map(renderItemRow).join('');
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
    if (nbData) {
      const st = litEl('litNbStatus');
      const link = litEl('litNbOpenLink');
      const base = `已同步 ${nbData.synced_count}/${nbData.total_with_pdf} 份 PDF · 已生成 ${nbData.reviewed_count} 篇 Review`;
      if (st) st.textContent = nbData.review_message ? `${base} ｜ ${nbData.review_message}` : base;
      if (link) {
        link.style.display = nbData.notebook_url ? 'inline-flex' : 'none';
        if (nbData.notebook_url) link.href = nbData.notebook_url;
      }
    }
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
   * Add pasted entries (if any) and trigger a background fetch or identify run.
   * @param {boolean} identifyOnly When true, only resolve metadata and APA 7.
   * @returns {Promise<void>}
   */
  async function handleAddAndProcess(identifyOnly) {
    const raw = litEl('litInputText')?.value.trim() || '';
    const courseCode = getSelectVal('litCourseSelectWrap') || null;
    const category = getSelectVal('litCategorySelectWrap') || '01 Material';
    const subfolder = litEl('litSubfolderInput')?.value.trim() || 'Literature_Review';
    const interactive = Boolean(litEl('litInteractiveCheck')?.checked);

    if (raw) {
      await litApi('/api/literature/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: raw, course_code: courseCode, category, subfolder }),
      });
      litEl('litInputText').value = '';
    }

    await litApi('/api/literature/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interactive, identify_only: identifyOnly }),
    });
    await refreshLiterature();
  }

  /**
   * Copy sorted APA 7 references to the clipboard preserving italic HTML formatting.
   * @returns {Promise<void>}
   */
  async function handleCopyApa() {
    const chosen = Array.from(selectedKeys);
    const qs = chosen.length > 0 ? `?keys=${encodeURIComponent(chosen.join(','))}` : '';
    const data = await litApi('/api/literature/export/apa' + qs);
    if (!data.count) {
      alert('目前沒有可產生的 APA 7 參考文獻。');
      return;
    }
    const box = litEl('litApaPreviewBox');
    const title = litEl('litApaPreviewTitle');
    const body = litEl('litApaPreviewBody');
    if (box && body) {
      if (title) title.textContent = `APA 7 參考文獻清單（共 ${data.count} 筆 · 已複製到剪貼簿）`;
      body.innerHTML = data.html;
      box.style.display = 'block';
    }
    if (navigator.clipboard && window.ClipboardItem) {
      const htmlBlob = new Blob([data.html], { type: 'text/html' });
      const textBlob = new Blob([data.plain], { type: 'text/plain' });
      await navigator.clipboard.write([new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob })]);
    } else if (navigator.clipboard) {
      await navigator.clipboard.writeText(data.plain);
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
        category: catSel?.getAttribute('data-value') || '01 Material',
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
   * Bind Gemini Literature Notebook sync, batch review, and Q&A search buttons.
   */
  function bindNotebookEvents() {
    litEl('litNbSyncBtn')?.addEventListener('click', async () => {
      const btn = litEl('litNbSyncBtn');
      if (btn) btn.textContent = '同步中…';
      try { await litApi('/api/literature/notebook/sync', { method: 'POST' }); await refreshLiterature(); }
      catch (e) { alert(e.message); } finally { if (btn) btn.textContent = '同步 PDF 至 Gemini'; }
    });
    litEl('litBatchReviewBtn')?.addEventListener('click', async () => {
      try {
        await litApi('/api/literature/reviews/batch', { method: 'POST' });
        await refreshLiterature();
      } catch (e) { alert(e.message); }
    });
    litEl('litNbQueryBtn')?.addEventListener('click', async () => {
      const q = litEl('litNbQueryInput')?.value.trim();
      if (!q) return;
      const btn = litEl('litNbQueryBtn');
      if (btn) btn.textContent = '查詢中…';
      try {
        const res = await litApi('/api/literature/notebook/ask', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question: q }),
        });
        const box = litEl('litNbAnswerBox'), body = litEl('litNbAnswerBody');
        if (box && body) { body.textContent = res.answer || '（無回覆）'; box.style.display = 'block'; }
      } catch (e) { alert(e.message); } finally { if (btn) btn.textContent = '查詢文獻'; }
    });
    litEl('litNbAnswerClose')?.addEventListener('click', () => {
      const box = litEl('litNbAnswerBox');
      if (box) box.style.display = 'none';
    });
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
    bindNotebookEvents();
    bindFilterAndSelectEvents();
    litEl('litStartBtn')?.addEventListener('click', () => handleAddAndProcess(false).catch(e => alert(e.message)));
    litEl('litIdentifyBtn')?.addEventListener('click', () => handleAddAndProcess(true).catch(e => alert(e.message)));
    litEl('litLookupMissingBtn')?.addEventListener('click', async () => {
      await litApi('/api/literature/process', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identify_only: true, no_browser: true }),
      });
      await refreshLiterature();
    });
    litEl('litCopyApaBtn')?.addEventListener('click', () => handleCopyApa().catch(e => alert(e.message)));
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
