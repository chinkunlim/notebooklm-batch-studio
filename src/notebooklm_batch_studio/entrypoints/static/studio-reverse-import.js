/**
 * Gemini Notebook 學習工作室 — optional reverse import from existing remote Gemini Notebooks.
 * Lets users browse remote notebooks, preview sources/artifacts, optionally import as a local course,
 * and download all sources & artifacts locally to DATA_DIR.
 */

let _remoteNotebooksCache = [];

/**
 * Switch the add-course modal step 1 between local folder picker and remote notebook reverse import.
 * @param {string} mode 'local' or 'remote'
 */
function switchAddMode(mode) {
  const isRemote = mode === 'remote';
  const localPane = document.getElementById('addLocalPane');
  const remotePane = document.getElementById('addRemotePane');
  const tabLocal = document.getElementById('tabAddLocal');
  const tabRemote = document.getElementById('tabAddRemote');
  if (localPane) localPane.style.display = isRemote ? 'none' : '';
  if (remotePane) remotePane.style.display = isRemote ? '' : 'none';
  if (tabLocal) tabLocal.className = isRemote ? 'btn btn-ghost btn-sm' : 'btn btn-primary btn-sm';
  if (tabRemote) tabRemote.className = isRemote ? 'btn btn-primary btn-sm' : 'btn btn-ghost btn-sm';
  if (isRemote && !_remoteNotebooksCache.length) loadRemoteNotebooksList();
}

/**
 * Fetch remote Gemini Notebooks and render the selectable list.
 * @returns {Promise<void>} Resolves when rendered
 */
async function loadRemoteNotebooksList() {
  const box = document.getElementById('remoteNotebooksList');
  const statusEl = document.getElementById('remoteNotebooksStatus');
  if (!box) return;
  if (statusEl) statusEl.textContent = '載入中…';
  try {
    const res = await fetch('/api/remote-notebooks');
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    _remoteNotebooksCache = data.notebooks || [];
    if (statusEl) statusEl.textContent = `共 ${_remoteNotebooksCache.length} 個遠端筆記本`;
    box.innerHTML = _remoteNotebooksCache.length
      ? _remoteNotebooksCache.map(renderRemoteNotebookRow).join('')
      : '<p class="small muted">目前雲端沒有筆記本。</p>';
  } catch (err) {
    if (statusEl) statusEl.textContent = '';
    box.innerHTML = `<p style="color:var(--danger)">讀取遠端筆記本失敗：${escHtml(err.message)}</p>`;
  }
}

/**
 * Render one remote notebook row with optional link badge and preview button.
 * @param {object} nb Remote notebook metadata
 * @returns {string} HTML string
 */
function renderRemoteNotebookRow(nb) {
  const linked = nb.linked_course_code
    ? `<span class="badge badge-success">已連結：${escHtml(nb.linked_course_code)}</span>`
    : '<span class="badge">尚未匯入</span>';
  return `<div class="row" style="justify-content:space-between;align-items:center;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius-sm)">
    <div><strong>${escHtml(nb.title || nb.id)}</strong> <span class="small muted">(${nb.sources_count || 0} 份來源)</span> ${linked}</div>
    <button type="button" class="btn btn-soft btn-sm" onclick="previewRemoteNotebookUi(${jsAttr(nb.id)})">預覽與選擇匯入</button>
  </div>`;
}

/**
 * Preview remote sources and artifacts for a selected notebook before importing.
 * @param {string} notebookId Remote notebook id
 * @returns {Promise<void>} Resolves when preview pane is rendered
 */
async function previewRemoteNotebookUi(notebookId) {
  const pane = document.getElementById('remoteNotebookPreview');
  if (!pane) return;
  pane.style.display = '';
  pane.innerHTML = '<p class="small muted">正在讀取筆記本來源與產出物…</p>';
  try {
    const res = await fetch(`/api/remote-notebooks/${encodeURIComponent(notebookId)}/preview`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    pane.innerHTML = renderRemotePreviewHtml(data);
  } catch (err) {
    pane.innerHTML = `<p style="color:var(--danger)">預覽失敗：${escHtml(err.message)}</p>`;
  }
}

/**
 * Render the remote notebook preview & import configuration form.
 * @param {object} data Preview payload with notebook, sources, and artifacts
 * @returns {string} HTML string
 */
function renderRemotePreviewHtml(data) {
  const nb = data.notebook || {};
  const sources = data.sources || [];
  const artifacts = data.artifacts || [];
  const srcChecks = sources.length
    ? sources.map(s => `<label class="cbox"><input type="checkbox" name="ri_src" value="${escAttr(s.id)}" checked>${escHtml(s.title || s.id)} <span class="small muted">(${escHtml(s.kind || 'source')})</span></label>`).join('')
    : '<p class="small muted">（無來源）</p>';
  return `<div class="stack" style="gap:10px">
    <div class="row" style="gap:10px;flex-wrap:wrap">
      <label class="opt-field" style="width:120px"><span>學期（必填）</span>
        <input type="text" id="riTerm" class="input" placeholder="113-2" />
      </label>
      <label class="opt-field" style="width:140px"><span>課號（選填）</span>
        <input type="text" id="riCourseNo" class="input" placeholder="CP30000" />
      </label>
      <label class="opt-field" style="flex:1;min-width:180px"><span>課程名稱</span>
        <input type="text" id="riCourseName" class="input" value="${escAttr(nb.title || '')}" />
      </label>
      <label class="opt-field" style="width:150px"><span>課程代碼（選填）</span>
        <input type="text" id="riCourseCode" class="input" value="${escAttr(nb.linked_course_code || '')}" placeholder="自動產生" />
      </label>
    </div>
    <div class="row" style="gap:14px;flex-wrap:wrap">
      <label class="cbox"><input type="checkbox" id="riRecordOnly" checked>只建學習紀錄並封存（不排生成）</label>
      <label class="cbox"><input type="checkbox" id="riDownloadSources" checked>下載來源全文為 Markdown 到本地</label>
      <label class="cbox"><input type="checkbox" id="riDownloadArtifacts" checked>下載所有雲端產出物（${artifacts.length} 件）到本地</label>
    </div>
    <div><span class="field-label">遠端來源（${sources.length} 份）</span><div class="checks">${srcChecks}</div></div>
    <div class="row" style="justify-content:flex-end;gap:8px">
      <button type="button" class="btn btn-primary" onclick="executeReverseImport(${jsAttr(nb.id)})">匯入課程並下載全部文件到本地</button>
    </div>
  </div>`;
}

/**
 * Submit reverse-import request and refresh course list + study portal.
 * @param {string} notebookId Remote notebook id
 * @returns {Promise<void>} Resolves when import completes
 */
async function executeReverseImport(notebookId) {
  const term = (document.getElementById('riTerm')?.value || '').trim();
  if (!term) {
    showToast('請先填寫學期（例如 113-2）', 'warning');
    return;
  }
  const srcIds = Array.from(document.querySelectorAll('input[name="ri_src"]:checked')).map(el => el.value);
  const payload = {
    term,
    course_no: (document.getElementById('riCourseNo')?.value || '').trim(),
    course_name: (document.getElementById('riCourseName')?.value || '').trim() || null,
    course_code: (document.getElementById('riCourseCode')?.value || '').trim() || null,
    record_only: Boolean(document.getElementById('riRecordOnly')?.checked ?? true),
    download_sources: Boolean(document.getElementById('riDownloadSources')?.checked),
    download_artifacts: Boolean(document.getElementById('riDownloadArtifacts')?.checked),
    source_ids: srcIds,
  };
  showToast('正在匯入筆記本並下載檔案到本地…', 'info', 2500);
  try {
    const res = await fetch(`/api/remote-notebooks/${encodeURIComponent(notebookId)}/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(
      `已匯入 ${data.course_code}：下載 ${data.downloaded_sources_count} 份來源、${data.synced_artifacts_count} 件產出`,
      'success',
      4000
    );
    closeAddModal();
    if (typeof fetchCourses === 'function') await fetchCourses();
    if (typeof initStudyPortal === 'function') await initStudyPortal();
  } catch (err) {
    showToast(`匯入失敗：${err.message}`, 'error');
  }
}
