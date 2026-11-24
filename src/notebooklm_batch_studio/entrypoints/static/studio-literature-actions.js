/**
 * Action handlers for the Literature Collection view (SPEC-012): job banner, Literature Notebook
 * status and buttons, add-and-process, and APA 7 copy. Split out of studio-literature.js; the
 * view passes in its refresh callback and selection instead of sharing closure state.
 */
(function () {
  'use strict';

  const { litApi, escapeHtml, getSelectVal } = window.LitUi;

  /**
   * Look up an element by its DOM id.
   * @param {string} id Element id.
   * @returns {HTMLElement|null} Matched element or null.
   */
  function litEl(id) {
    return document.getElementById(id);
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
   * Show Literature Notebook sync counts, the batch Review message, and the notebook link.
   * @param {object} nbData Response payload from `/api/literature/notebook`.
   */
  function renderNotebookStatus(nbData) {
    const st = litEl('litNbStatus');
    const link = litEl('litNbOpenLink');
    const base = `已同步 ${nbData.synced_count}/${nbData.total_with_pdf} 份 PDF · 已生成 ${nbData.reviewed_count} 篇 Review`;
    if (st) st.textContent = nbData.review_message ? `${base} ｜ ${nbData.review_message}` : base;
    if (link) {
      const safeUrl = typeof safeHttpUrl === 'function' ? safeHttpUrl(nbData.notebook_url) : '';
      link.style.display = safeUrl ? 'inline-flex' : 'none';
      if (safeUrl) link.href = safeUrl;
      else link.removeAttribute('href');
    }
  }

  /**
   * Add pasted entries (if any) and trigger a background fetch or identify run.
   * @param {boolean} identifyOnly When true, only resolve metadata and APA 7.
   * @param {Function} refresh Callback that reloads the literature view.
   * @returns {Promise<void>}
   */
  async function handleAddAndProcess(identifyOnly, refresh) {
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
    await refresh();
  }

  /**
   * Copy sorted APA 7 references to the clipboard preserving italic HTML formatting.
   * @param {Set<string>} selectedKeys Keys of the ticked rows (all items when empty).
   * @returns {Promise<void>}
   */
  async function handleCopyApa(selectedKeys) {
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
   * Bind Gemini Literature Notebook sync, batch review, and Q&A search buttons.
   * @param {Function} refreshLiterature Callback that reloads the literature view.
   */
  function bindNotebookEvents(refreshLiterature) {
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

  window.LitActions = { renderJobBanner, renderNotebookStatus, handleAddAndProcess, handleCopyApa, bindNotebookEvents };
})();
