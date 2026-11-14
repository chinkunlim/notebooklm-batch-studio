/* Gemini Notebook 學習工作室 — Remote artifacts management panel: lists remote Gemini Notebook
   artifacts, highlights which version is currently active on the study page to prevent accidental
   deletion, and supports syncing back to web UI or deleting remote/local artifacts. */

/**
 * Fetch and render remote Gemini Notebook artifacts for a course.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when rendered
 */
async function loadCourseRemoteArtifacts(code) {
  const box = document.getElementById('detailRemoteArtifacts');
  const sum = document.getElementById('detailRemoteArtifactsSummary');
  if (!box) return;
  try {
    const res = await fetch(`/api/courses/${code}/remote-artifacts`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const items = data.artifacts || [];
    const activeN = items.filter(a => a.is_latest_active).length;
    if (sum) sum.textContent = `遠端 ${items.length} 件產出物 · 目前使用中 ${activeN} 件`;
    box.innerHTML = remoteArtifactsToolbarHtml(code) + remoteArtifactsTableHtml(items, code);
  } catch (err) {
    box.innerHTML = `<p style="color:var(--danger)">雲端產出物載入失敗：${escHtml(err.message)}</p>`;
  }
}

/**
 * Render the toolbar for remote artifacts management.
 * @param {string} code Course code
 * @returns {string} HTML toolbar string
 */
function remoteArtifactsToolbarHtml(code) {
  return `<div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center">
    <button type="button" class="btn btn-ghost btn-sm" onclick="loadCourseRemoteArtifacts('${escAttr(code)}')">重新整理雲端清單</button>
    <button type="button" class="btn btn-primary btn-sm" onclick="syncRemoteArtifactsNow('${escAttr(code)}')">同步回網頁</button>
  </div>`;
}

/**
 * Render the remote artifacts table with active-version badges.
 * @param {Array<object>} items Annotated remote artifact objects
 * @param {string} code Course code
 * @returns {string} HTML table string
 */
function remoteArtifactsTableHtml(items, code) {
  if (!items.length) return '<p class="small muted">遠端筆記本目前沒有產出物。</p>';
  const rows = items.map(a => remoteArtifactRowHtml(a, code)).join('');
  return `<table><thead><tr><th>名稱</th><th>類型</th><th>使用狀態（防誤刪）</th><th>雲端 ID</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

/**
 * Render one row in the remote artifacts table.
 * @param {object} art Annotated remote artifact
 * @param {string} code Course code
 * @returns {string} HTML row string
 */
function remoteArtifactRowHtml(art, code) {
  const title = art.title || art.id;
  const ver = art.local_version ? `v${art.local_version}` : '';
  let badge = '<span class="badge">未同步至網頁</span>';
  if (art.is_latest_active) badge = `<span class="badge badge-success">⭐ 目前使用中 (${ver})</span>`;
  else if (art.in_use) badge = `<span class="badge badge-warning">舊版保留 (${ver})</span>`;
  const scope = art.lecture_no ? `L${pad2(art.lecture_no)}` : (art.artifact_type ? '全課程' : '—');
  return `<tr><td><code>${escHtml(title)}</code><div class="job-sub">${scope}</div></td>
    <td>${escHtml(art.kind || art.artifact_type || '—')}</td><td>${badge}</td><td><code>${escHtml(art.id)}</code></td>
    <td><button type="button" class="btn btn-ghost btn-sm" style="color:var(--danger)"
      data-code="${escAttr(code)}" data-id="${escAttr(art.id)}" data-title="${escAttr(title)}"
      data-active="${art.is_latest_active ? '1' : '0'}" data-ver="${escAttr(ver)}"
      onclick="deleteRemoteArtifactUi(this)">刪除</button></td></tr>`;
}

/**
 * Sync remote artifacts back to local storage and refresh course details.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when synced
 */
async function syncRemoteArtifactsNow(code) {
  try {
    const res = await fetch(`/api/courses/${code}/sync`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已同步 ${data.synced_count || 0} 件雲端產出物至網頁`, 'success', 2400);
    await loadCourseRemoteArtifacts(code);
    if (typeof loadCourseDetails === 'function') loadCourseDetails(code, true);
  } catch (err) {
    showToast(`同步失敗：${err.message}`, 'error');
  }
}

/**
 * Confirm and delete a remote artifact with extra warning when it is currently active.
 * @param {HTMLElement} btn Delete button carrying data-* attributes
 * @returns {Promise<void>} Resolves when deleted or cancelled
 */
async function deleteRemoteArtifactUi(btn) {
  const { code, id: artifactId, title, active, ver: versionLabel } = btn.dataset;
  const isActive = active === '1';
  const warn = isActive
    ? `⚠️ 注意：「${title}」是研讀頁面【目前正在使用的版本 ${versionLabel}】！\n刪除後將一併移除本機對應檔案，確定要從 Google Notebook 刪除嗎？`
    : `確定要從 Google Notebook 刪除「${title}」嗎？`;
  if (!(await askConfirm(warn, { okLabel: '確認刪除', danger: true }))) return;
  try {
    const url = `/api/courses/${code}/remote-artifacts/${encodeURIComponent(artifactId)}?delete_local=${isActive ? 'true' : 'false'}`;
    const res = await fetch(url, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已從雲端刪除「${title}」`, 'info', 2200);
    await loadCourseRemoteArtifacts(code);
    if (typeof loadCourseDetails === 'function') loadCourseDetails(code, true);
  } catch (err) {
    showToast(`刪除失敗：${err.message}`, 'error');
  }
}
