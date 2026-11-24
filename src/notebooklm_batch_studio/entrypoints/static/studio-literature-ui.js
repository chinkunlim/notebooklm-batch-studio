/**
 * UI & PDF.js preview helpers for the Literature Collection view (`#view-literature`).
 * Provides HTML escaping, dark custom `.lit-select` dropdown state/events,
 * and inline collapsible PDF.js canvas rendering with zoom controls.
 */
(function () {
  'use strict';

  let pdfRenderToken = 0;
  let litScale = Number(localStorage.getItem('v05.litPdfScale') || 1.25);
  if (litScale < 0.85 || litScale > 2.0) litScale = 1.25;
  let activePdfDoc = null;
  let activePdfUrl = '';

  /**
   * Look up an element by its DOM id.
   * @param {string} id Element id.
   * @returns {HTMLElement|null} Matched element or null.
   */
  function byId(id) {
    return document.getElementById(id);
  }

  /**
   * Escape HTML special characters in untrusted text.
   * @param {string} text Raw text.
   * @returns {string} Escaped HTML text.
   */
  function escapeHtml(text) {
    if (typeof window.escHtml === 'function') return window.escHtml(text);
    return String(text ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * Read the selected value from a custom `.lit-select` wrapper.
   * @param {string} wrapId Wrapper element id.
   * @returns {string} Selected value string.
   */
  function getSelectVal(wrapId) {
    return byId(wrapId)?.getAttribute('data-value') || '';
  }

  /**
   * Update a custom `.lit-select` wrapper's value, button text, and active option highlight.
   * @param {string} wrapId Wrapper element id.
   * @param {string} val Selected value.
   * @param {string} [label] Optional display text override.
   */
  function setSelectVal(wrapId, val, label) {
    const wrap = byId(wrapId);
    if (!wrap) return;
    wrap.setAttribute('data-value', val);
    const opts = wrap.querySelectorAll('.lit-select-opt');
    let text = label;
    opts.forEach(o => {
      const match = o.getAttribute('data-val') === val;
      o.classList.toggle('on', match);
      if (match && !text) text = o.textContent;
    });
    const txtEl = wrap.querySelector('.lit-sel-txt');
    if (txtEl && text !== undefined) txtEl.textContent = text;
  }

  /**
   * Bind open/close and option-selection events for all `.lit-select` menus inside a container.
   * @param {string} containerId Root container element id.
   * @param {(wrapId: string, val: string) => void} onSelect Callback when an option is chosen.
   */
  function bindLitSelectMenu(containerId, onSelect) {
    byId(containerId)?.addEventListener('click', ev => {
      const t = ev.target;
      if (!(t instanceof Element)) return;
      const opt = t.closest('.lit-select-opt');
      if (opt) {
        const wrap = opt.closest('.lit-select');
        if (wrap) {
          const val = opt.getAttribute('data-val') || '';
          setSelectVal(wrap.id, val, opt.textContent || '');
          wrap.classList.remove('open');
          if (onSelect) onSelect(wrap.id, val);
        }
        return;
      }
      const btn = t.closest('.lit-select-btn');
      if (btn) {
        const wrap = btn.closest('.lit-select');
        const wasOpen = wrap?.classList.contains('open');
        document.querySelectorAll(`#${containerId} .lit-select.open`).forEach(s => s.classList.remove('open'));
        if (wrap && !wasOpen) wrap.classList.add('open');
      }
    });
  }

  /**
   * Return the current inline PDF preview scale.
   * @returns {number} Scale factor (0.85..2.0).
   */
  function getLitScale() {
    return litScale;
  }

  /**
   * Render the collapsible PDF or Literature Review row directly beneath an expanded item row.
   * @param {object} item Serialized literature item.
   * @param {string|null} expandedPdfKey Currently expanded PDF item key.
   * @param {string|null} expandedReviewKey Currently expanded review item key.
   * @returns {string} HTML `<tr>` markup or empty string.
   */
  function renderExpandRowHtml(item, expandedPdfKey, expandedReviewKey) {
    if (expandedReviewKey === item.key && item.review_markdown) {
      return `
        <tr class="lit-expand-row">
          <td colspan="4">
            <div class="lit-expand-box">
              <div class="lit-expand-bar">
                <strong style="flex:1">Literature Review — ${escapeHtml(item.key)}</strong>
                <button class="btn btn-xs btn-soft" data-lit-review-regen="${escapeHtml(item.key)}">重新生成</button>
                <button class="icon-btn" data-lit-review="${escapeHtml(item.key)}" aria-label="關閉"><i class="icon-x"></i></button>
              </div>
              <div class="lit-review-body">${escapeHtml(item.review_markdown)}</div>
            </div>
          </td>
        </tr>`;
    }
    if (expandedPdfKey !== item.key || !item.file_url) return '';
    return `
      <tr class="lit-expand-row">
        <td colspan="4">
          <div class="lit-expand-box">
            <div class="lit-expand-bar">
              <strong style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(item.file || item.key)}</strong>
              <span class="small muted" id="litExpandPageCount">載入中…</span>
              <button class="icon-btn" data-lit-zoom="-0.15" aria-label="縮小" title="縮小"><i class="icon-zoom-out"></i></button>
              <button type="button" class="reader-zoom-pill" data-lit-zoom-cycle="1" id="litZoomLabel" title="點擊切換 小(100%) / 中(135%) / 大(175%)">${Math.round(litScale * 100)}%</button>
              <button class="icon-btn" data-lit-zoom="0.15" aria-label="放大" title="放大"><i class="icon-zoom-in"></i></button>
              <button class="icon-btn" data-lit-view="${escapeHtml(item.key)}" aria-label="關閉預覽" title="關閉預覽"><i class="icon-x"></i></button>
            </div>
            <div class="lit-expand-pages" id="litExpandPages" data-pdf-url="${escapeHtml(item.file_url)}">
              <div class="small muted" style="padding:20px">正在載入 PDF 預覽…</div>
            </div>
          </div>
        </td>
      </tr>`;
  }

  /**
   * Render pages of an already-loaded PDF.js document at `litScale`.
   * @param {object} doc Loaded PDF.js document.
   * @param {number} token Render cancellation token.
   * @returns {Promise<void>}
   */
  async function renderPdfPages(doc, token) {
    const container = byId('litExpandPages');
    const countEl = byId('litExpandPageCount');
    if (!container) return;
    if (countEl) countEl.textContent = `共 ${doc.numPages} 頁`;
    container.innerHTML = '';
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const maxPages = Math.min(doc.numPages, 30);
    for (let n = 1; n <= maxPages; n++) {
      if (token !== pdfRenderToken) return;
      const page = await doc.getPage(n);
      const viewport = page.getViewport({ scale: litScale });
      const canvas = document.createElement('canvas');
      canvas.className = 'lit-expand-page-canvas';
      canvas.width = Math.floor(viewport.width * dpr);
      canvas.height = Math.floor(viewport.height * dpr);
      canvas.style.width = `${Math.floor(viewport.width)}px`;
      container.appendChild(canvas);
      const ctx = canvas.getContext('2d');
      await page.render({ canvasContext: ctx, viewport, transform: [dpr, 0, 0, dpr, 0, 0] }).promise;
    }
    if (doc.numPages > maxPages) {
      const note = document.createElement('div');
      note.className = 'small muted';
      note.textContent = `僅預覽前 ${maxPages} 頁（共 ${doc.numPages} 頁）`;
      container.appendChild(note);
    }
  }

  /**
   * Load (or reuse cached) PDF.js document and render it inline without triggering downloads.
   * @param {string} url PDF endpoint URL.
   * @returns {Promise<void>}
   */
  async function mountInlinePdf(url) {
    const container = byId('litExpandPages');
    if (!container || !url) return;
    const token = ++pdfRenderToken;
    try {
      if (activePdfDoc && activePdfUrl === url) {
        return renderPdfPages(activePdfDoc, token);
      }
      const pdfjsLib = await import('/static/vendor/pdfjs/pdf.min.mjs');
      pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/vendor/pdfjs/pdf.worker.min.mjs';
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const buf = await resp.arrayBuffer();
      if (token !== pdfRenderToken) return;
      activePdfDoc = await pdfjsLib.getDocument({ data: new Uint8Array(buf) }).promise;
      activePdfUrl = url;
      if (token !== pdfRenderToken) return;
      await renderPdfPages(activePdfDoc, token);
    } catch (err) {
      if (token === pdfRenderToken) {
        container.innerHTML = `<div class="small muted" style="padding:20px">PDF 預覽失敗：${escapeHtml(err.message)}</div>`;
      }
    }
  }

  /**
   * Apply a new zoom scale to the inline literature PDF preview and persist it.
   * @param {number} next Target scale (clamped 0.85..2.0).
   */
  function applyLitScale(next) {
    litScale = Math.min(2.0, Math.max(0.85, Number(next.toFixed(2))));
    try { localStorage.setItem('v05.litPdfScale', String(litScale)); } catch (_) {}
    const lbl = byId('litZoomLabel');
    if (lbl) lbl.textContent = `${Math.round(litScale * 100)}%`;
    if (activePdfDoc) renderPdfPages(activePdfDoc, ++pdfRenderToken).catch(console.error);
  }

  /**
   * Build the Excel-style sort + filter popover HTML for a table column.
   * @param {object} opts Popover options (`col`, `items`, `sortRules`, `activeSet`, `valGetter`, `apaQuery`).
   * @returns {string} HTML markup for `.lit-col-pop`.
   */
  function renderExcelColPopoverHtml(opts) {
    const { col, items, sortRules, activeSet, valGetter, apaQuery } = opts;
    const rule = sortRules.find(r => r.col === col);
    const clearBtn = rule ? `<button type="button" class="lit-col-pop-btn" data-lit-col-sort="${col}:none"><i class="icon-x"></i>取消此欄排序</button>` : '';
    let filterBody = '';
    if (col === 'apa') {
      const q = escapeHtml(apaQuery || '');
      const clearSearch = q ? `<button type="button" class="lit-col-pop-btn" data-lit-clear-search="apa"><i class="icon-x"></i>清除關鍵字篩選</button>` : '';
      filterBody = `<div style="display:flex;flex-direction:column;gap:6px"><input type="text" class="input lit-col-search" data-lit-col-search="apa" value="${q}" placeholder="搜尋作者、年份、標題、DOI…" />${clearSearch}</div>`;
    } else {
      const counts = new Map();
      items.forEach(it => {
        const v = valGetter(it, col);
        counts.set(v, (counts.get(v) || 0) + 1);
      });
      const allChecked = !activeSet || Array.from(counts.keys()).every(k => activeSet.has(k));
      const listHtml = Array.from(counts.entries()).map(([val, cnt]) => {
        const chk = !activeSet || activeSet.has(val) ? ' checked' : '';
        return `<label class="lit-col-pop-chk"><input type="checkbox" data-lit-col-val="${escapeHtml(val)}" data-lit-col="${col}"${chk} /><span>${escapeHtml(val)}</span><em>${cnt}</em></label>`;
      }).join('');
      filterBody = `<div class="lit-col-pop-list"><label class="lit-col-pop-chk"><input type="checkbox" data-lit-col-all="${col}"${allChecked ? ' checked' : ''} /><span><strong>全選 / 清除篩選</strong></span></label>${listHtml}</div>`;
    }
    return `
      <div class="lit-col-pop${col === 'target' ? ' right' : ''}" data-lit-pop="${col}">
        <div class="lit-col-pop-sec">
          <button type="button" class="lit-col-pop-btn${rule?.dir === 'asc' ? ' on' : ''}" data-lit-col-sort="${col}:asc">${caretSvg('up')}升冪排序</button>
          <button type="button" class="lit-col-pop-btn${rule?.dir === 'desc' ? ' on' : ''}" data-lit-col-sort="${col}:desc">${caretSvg('down')}降冪排序</button>
          ${clearBtn}
        </div>
        ${filterBody}
      </div>`;
  }

  /**
   * Return a mathematically centered 12x12 SVG chevron so up/down arrows have zero font baseline shift.
   * @param {'up'|'down'} dir Arrow direction.
   * @returns {string} Inline SVG markup.
   */
  function caretSvg(dir) {
    const d = dir === 'up' ? 'M2.5 7.75L6 4.25L9.5 7.75' : 'M2.5 4.25L6 7.75L9.5 4.25';
    return `<svg class="lit-caret" width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`;
  }

  /**
   * Call a JSON API endpoint and throw on non-OK HTTP responses.
   * @param {string} url Request URL.
   * @param {RequestInit} [opts] Fetch options.
   * @returns {Promise<any>} Parsed JSON body.
   */
  async function litApi(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) {
      let msg = res.statusText;
      try {
        const data = await res.json();
        msg = data.detail || msg;
      } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }

  /**
   * Map a literature item status to a CSS badge class.
   * @param {string} status Status code.
   * @returns {string} CSS class string.
   */
  function statusBadgeClass(status) {
    if (status === 'downloaded') return 'badge ok';
    if (status === 'downloaded_copy') return 'badge info';
    if (status === 'needs_review' || status === 'borrow') return 'badge warn';
    if (status === 'not_found' || status === 'unavailable') return 'badge err';
    return 'badge';
  }

  /**
   * Return a concise status badge label without duplicating version notes in the status column.
   * @param {object} item Serialized literature item.
   * @returns {string} Short badge label.
   */
  function shortStatusLabel(item) {
    if (item.status === 'downloaded') return '✅ 已下載';
    if (item.status === 'downloaded_copy') return '🟡 已下載';
    return item.status_label || item.status;
  }

  window.LitUi = {
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
  };
})();
