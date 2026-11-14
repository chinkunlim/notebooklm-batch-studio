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
  const c = escAttr(code);
  return `<div class="row" style="flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center">
    <button type="button" class="btn btn-ghost btn-sm" onclick="loadCourseRemoteArtifacts('${c}')">重新整理雲端清單</button>
    <button type="button" class="btn btn-primary btn-sm" onclick="syncRemoteArtifactsNow('${c}')">同步回網頁</button>
    <button type="button" class="btn btn-ghost btn-sm" onclick="suggestRemoteReportsUi('${c}')">💡 AI 建議報告</button>
    <button type="button" class="btn btn-ghost btn-sm" onclick="generateCustomReportUi('${c}')">📝 自訂報告</button>
    <button type="button" class="btn btn-ghost btn-sm" onclick="generateCinematicVideoUi('${c}')">🎬 生成電影感影片</button>
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
  const kind = String(art.kind || art.artifact_type || '').toLowerCase();
  const attrs = `data-code="${escAttr(code)}" data-id="${escAttr(art.id)}" data-title="${escAttr(title)}" data-kind="${escAttr(kind)}"`;
  const slideBtn = kind.includes('slide') ? `<button type="button" class="btn btn-ghost btn-sm" ${attrs} onclick="reviseRemoteSlideUi(this)">✏️ 微調投影片</button>` : '';
  const expBtn = (kind.includes('report') || kind.includes('table')) ? `<button type="button" class="btn btn-ghost btn-sm" ${attrs} onclick="exportRemoteArtifactUi(this)">📤 匯出 Docs/Sheets</button>` : '';
  return `<tr><td><code>${escHtml(title)}</code><div class="job-sub">${scope}</div></td>
    <td>${escHtml(art.kind || art.artifact_type || '—')}</td><td>${badge}</td><td><code>${escHtml(art.id)}</code></td>
    <td class="row" style="gap:4px;flex-wrap:wrap">${slideBtn}${expBtn}
      <button type="button" class="btn btn-ghost btn-sm" ${attrs} onclick="retryRemoteArtifactUi(this)">🔄 遠端重試</button>
      <button type="button" class="btn btn-ghost btn-sm" style="color:var(--danger)" ${attrs}
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

/**
 * Fetch and display AI-suggested report topics for the course notebook.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when suggestions are shown
 */
async function suggestRemoteReportsUi(code) {
  try {
    const res = await fetch(`/api/courses/${code}/remote-artifacts/suggest-reports`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const items = data.suggestions || [];
    if (!items.length) { showToast('目前沒有建議報告', 'info'); return; }
    const text = items.map((s, i) => `${i + 1}. ${s.title} (${s.audience_level || 'general'})\n   ${s.description || ''}`).join('\n\n');
    const pick = window.prompt(`${text}\n\n輸入編號（1–${items.length}）即可直接生成自訂報告，留空取消：`, '');
    const idx = Number(pick) - 1;
    if (pick && idx >= 0 && idx < items.length) {
      await triggerScopedGenerate(code, 'custom_report', null, items[idx].prompt || items[idx].title);
    }
  } catch (err) {
    showToast(`取得 AI 建議報告失敗：${err.message}`, 'error');
  }
}

/**
 * Prompt for instructions and optional lecture number to trigger cinematic video generation.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when request finishes
 */
async function generateCinematicVideoUi(code) {
  const lecRaw = window.prompt('要為第幾講生成電影感影片？（留空代表全課程）：', '');
  if (lecRaw === null) return;
  const instructions = window.prompt('請輸入電影感影片的敘事風格或重點指令（可留空使用預設）：', '');
  if (instructions === null) return;
  const lecNo = lecRaw.trim() ? Number(lecRaw.trim()) : null;
  try {
    const res = await fetch(`/api/courses/${code}/remote-artifacts/cinematic-video`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instructions: instructions.trim(), lecture_no: lecNo || null }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已觸發電影感影片生成 (${data.artifact_id || 'ok'})`, 'success', 2600);
    await loadCourseRemoteArtifacts(code);
  } catch (err) {
    showToast(`生成電影感影片失敗：${err.message}`, 'error');
  }
}

/**
 * Prompt for slide index and prompt to revise a remote slide deck.
 * @param {HTMLElement} btn Button carrying data-code and data-id
 * @returns {Promise<void>} Resolves when revision finishes
 */
async function reviseRemoteSlideUi(btn) {
  const { code, id } = btn.dataset;
  const idxRaw = window.prompt('要微調第幾頁投影片（從 0 開始）？', '0');
  if (idxRaw === null) return;
  const prompt = window.prompt('請輸入該頁投影片的微調指令：', '');
  if (!prompt || !prompt.trim()) return;
  try {
    const res = await fetch(`/api/courses/${code}/remote-artifacts/${encodeURIComponent(id)}/revise-slide`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slide_index: Number(idxRaw) || 0, prompt: prompt.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast('已送出投影片微調', 'success', 2400);
    await loadCourseRemoteArtifacts(code);
  } catch (err) {
    showToast(`微調投影片失敗：${err.message}`, 'error');
  }
}

/**
 * Export a remote report or data table to Google Docs or Google Sheets.
 * @param {HTMLElement} btn Button carrying data-code, data-id, data-title, data-kind
 * @returns {Promise<void>} Resolves when export finishes
 */
async function exportRemoteArtifactUi(btn) {
  const { code, id, title, kind } = btn.dataset;
  const exportKind = kind.includes('table') ? 'data_table' : 'report';
  const docTitle = window.prompt('請輸入匯出至 Google Docs / Sheets 的標題：', title || id);
  if (!docTitle || !docTitle.trim()) return;
  try {
    const res = await fetch(`/api/courses/${code}/remote-artifacts/${encodeURIComponent(id)}/export`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: docTitle.trim(), kind: exportKind }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已匯出至 Google ${exportKind === 'data_table' ? 'Sheets' : 'Docs'}`, 'success', 2600);
  } catch (err) {
    showToast(`匯出失敗：${err.message}`, 'error');
  }
}

/**
 * Retry a failed remote artifact generation task.
 * @param {HTMLElement} btn Button carrying data-code, data-id, data-title
 * @returns {Promise<void>} Resolves when retry request finishes
 */
async function retryRemoteArtifactUi(btn) {
  const { code, id, title } = btn.dataset;
  if (!(await askConfirm(`確定要遠端重試「${title}」嗎？`, { okLabel: '確認重試' }))) return;
  try {
    const res = await fetch(`/api/courses/${code}/remote-artifacts/${encodeURIComponent(id)}/retry`, {
      method: 'POST',
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已重試「${title}」`, 'success', 2200);
    await loadCourseRemoteArtifacts(code);
  } catch (err) {
    showToast(`重試失敗：${err.message}`, 'error');
  }
}

/**
 * Prompt for a Web or YouTube URL and import it as a notebook source.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when import finishes
 */
async function addUrlSourceUi(code) {
  const url = window.prompt('請輸入網頁或 YouTube 網址：', 'https://');
  if (!url || !url.trim() || url.trim() === 'https://') return;
  const title = window.prompt('自訂來源標題（可留空）：', '');
  try {
    const res = await fetch(`/api/courses/${code}/sources/url`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: url.trim(), title: title && title.trim() ? title.trim() : null }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已加入網址來源「${data.title || url.trim()}」`, 'success', 2400);
    if (typeof loadCourseSources === 'function') await loadCourseSources(code);
  } catch (err) {
    showToast(`加入網址來源失敗：${err.message}`, 'error');
  }
}

/**
 * Prompt for title and plain text content and import it as a notebook source.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when import finishes
 */
async function addTextSourceUi(code) {
  const title = window.prompt('請輸入純文字來源標題：', '補充筆記');
  if (!title || !title.trim()) return;
  const content = window.prompt('請貼上來源文字內容：', '');
  if (!content || !content.trim()) return;
  try {
    const res = await fetch(`/api/courses/${code}/sources/text`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title.trim(), content: content.trim() }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已加入純文字來源「${data.title || title.trim()}」`, 'success', 2400);
    if (typeof loadCourseSources === 'function') await loadCourseSources(code);
  } catch (err) {
    showToast(`加入純文字來源失敗：${err.message}`, 'error');
  }
}

/**
 * Run fast or deep web research and optionally import discovered sources.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when research and optional import finish
 */
async function researchSourcesUi(code) {
  const query = window.prompt('請輸入網路研究關鍵字：', '');
  if (!query || !query.trim()) return;
  const modeRaw = window.prompt('請選擇研究模式（fast 或 deep）：', 'fast');
  if (modeRaw === null) return;
  const mode = modeRaw.trim().toLowerCase() === 'deep' ? 'deep' : 'fast';
  try {
    const res = await fetch(`/api/courses/${code}/sources/research`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query.trim(), mode }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    await importSelectedResearch(code, data);
  } catch (err) {
    showToast(`網路研究失敗：${err.message}`, 'error');
  }
}

/**
 * Confirm and import discovered web research sources into the course notebook.
 * @param {string} code Course code
 * @param {object} data Research response containing task_id, summary, and sources
 * @returns {Promise<void>} Resolves when import completes or is skipped
 */
async function importSelectedResearch(code, data) {
  const found = (data.sources || []).slice(0, 5);
  if (!found.length) { showToast('未搜尋到可匯入的網路來源', 'info'); return; }
  const preview = found.map((s, i) => `${i + 1}. ${s.title || s.url}`).join('\n');
  if (!(await askConfirm(`搜尋到 ${found.length} 筆來源：\n${preview}\n\n是否全部匯入筆記本？`, { okLabel: '確認匯入' }))) return;
  const res = await fetch(`/api/courses/${code}/sources/research/import`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: data.task_id, sources: found.map(s => ({ url: s.url, title: s.title || s.url })) }),
  });
  const imp = await res.json();
  if (!res.ok) throw new Error(imp.detail || res.statusText);
  showToast(`已匯入 ${imp.imported_count || found.length} 筆研究來源`, 'success', 2400);
  if (typeof loadCourseSources === 'function') await loadCourseSources(code);
}

/**
 * Prompt for a custom report prompt and generate ReportFormat.CUSTOM.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when generation request finishes
 */
async function generateCustomReportUi(code) {
  const instructions = window.prompt('請輸入完全自訂報告的格式與內容指令：', '');
  if (!instructions || !instructions.trim()) return;
  await triggerScopedGenerate(code, 'custom_report', null, instructions.trim());
}

/**
 * Generate a Studio artifact scoped to checked source checkboxes in the Sources tab.
 * @param {string} code Course code
 * @returns {Promise<void>} Resolves when generation request finishes
 */
async function generateFromSelectedSourcesUi(code) {
  const picked = [...document.querySelectorAll('.src-pick:checked')].map(el => el.value);
  if (!picked.length) { showToast('請先在來源清單勾選至少一個來源', 'info'); return; }
  const kind = window.prompt(
    `已選 ${picked.length} 個來源。請輸入產出類型（custom_report / audio / video / cinematic_video / infographic / slide_deck / quiz / flashcards / mind_map / data_table）：`,
    'custom_report',
  );
  if (!kind || !kind.trim()) return;
  const instructions = window.prompt('請輸入生成指令或重點（可留空）：', '');
  if (instructions === null) return;
  await triggerScopedGenerate(code, kind.trim(), picked, instructions.trim());
}

/**
 * Call POST /api/courses/{code}/remote-artifacts/generate with scoped sources.
 * @param {string} code Course code
 * @param {string} kind Artifact kind
 * @param {Array<string>|null} sourceIds Selected source IDs or null for all
 * @param {string} instructions Prompt or extra instructions
 * @returns {Promise<void>} Resolves when generation finishes
 */
async function triggerScopedGenerate(code, kind, sourceIds, instructions) {
  try {
    const res = await fetch(`/api/courses/${code}/remote-artifacts/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, source_ids: sourceIds, instructions }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已依 ${data.source_count || '全部'} 筆來源生成 ${kind} (${data.artifact_id || 'ok'})`, 'success', 2600);
    await loadCourseRemoteArtifacts(code);
  } catch (err) {
    showToast(`生成失敗：${err.message}`, 'error');
  }
}
