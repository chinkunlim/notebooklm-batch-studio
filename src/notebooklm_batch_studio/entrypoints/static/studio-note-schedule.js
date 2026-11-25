/**
 * 筆記排程 (SPEC-020): approve chapters once, then Gemini notes are generated in the background one by one.
 * When Gemini's quota runs out the schedule waits for the reset time shown here and continues by itself.
 * Uses escHtml / jsAttr (studio-escape.js), showToast / askConfirm (studio.js).
 */

const _NS_STATUS = {
  pending: '等待中', running: '生成中', quota_wait: '等待額度', done: '完成', failed: '失敗',
};

/**
 * Format an ISO time as local "HH:MM" (today) or "M/D HH:MM".
 * @param {string} iso ISO timestamp
 * @returns {string} Human-readable time
 */
function fmtResumeTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  return d.toDateString() === new Date().toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
}

/**
 * Call a schedule endpoint and return its JSON (throws the server's `detail`).
 * @param {string} url Full endpoint path under /api/notes/schedule
 * @param {object} [body] JSON body for POST
 * @returns {Promise<object>} Parsed response
 */
async function _nsApi(url, body) {
  const opts = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

/**
 * Render the card skeleton once (course picker, chapter list, buttons, status list).
 * @param {HTMLElement} card Host element
 * @returns {Promise<void>}
 */
async function _nsRenderSkeleton(card) {
  const courses = await fetch('/api/courses').then(r => r.json()).catch(() => []);
  const opts = (courses || []).filter(c => c.status !== 'archived')
    .map(c => `<option value="${escHtml(c.code)}">${escHtml(c.code)}　${escHtml(c.name)}</option>`).join('');
  card.innerHTML = `<div class="card-head"><h2 class="h2">筆記排程</h2><span id="nsBanner" class="small muted"></span></div>
    <p class="small muted" style="margin-bottom:8px">勾選章節按「開始排程」後，會在背景依序用 Gemini 生成；額度用完會等重置時間到了自動繼續（網頁伺服器要開著）。</p>
    <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px">
      <select id="nsCourse" class="input" onchange="loadNoteScheduleCandidates()"><option value="">選擇課程…</option>${opts}</select>
      <button class="btn btn-primary btn-sm" onclick="startNoteSchedule()">開始排程</button>
      <button class="btn btn-soft btn-sm" id="nsPauseBtn" onclick="toggleNoteSchedulePause()">暫停排程</button>
      <button class="btn btn-ghost btn-sm" onclick="clearFinishedNoteSchedule()">清除已完成</button>
    </div>
    <div id="nsCandidates" class="row" style="gap:6px 14px;flex-wrap:wrap;margin-bottom:10px"></div>
    <div id="nsItems" class="stack small"></div>`;
  card.dataset.ready = '1';
}

/**
 * List the chosen course's chapters with checkboxes (chapters without notes are pre-checked).
 * @returns {Promise<void>}
 */
async function loadNoteScheduleCandidates() {
  const code = document.getElementById('nsCourse')?.value;
  const host = document.getElementById('nsCandidates');
  if (!host) return;
  if (!code) { host.innerHTML = ''; return; }
  try {
    const data = await _nsApi(`/api/notes/schedule/candidates/${encodeURIComponent(code)}`);
    host.innerHTML = (data.chapters || []).map(c => {
      const busy = c.scheduled && !['done', 'failed'].includes(c.scheduled);
      const note = busy ? `（${_NS_STATUS[c.scheduled] || c.scheduled}）` : (c.has_note ? '（已有筆記）' : '');
      return `<label class="small"><input type="checkbox" class="ns-pick" value="${c.lecture_no}" ${!c.has_note && !busy ? 'checked' : ''} ${busy ? 'disabled' : ''}>
        L${String(c.lecture_no).padStart(2, '0')} ${escHtml(c.title)}${note}</label>`;
    }).join('') || '<span class="small muted">這門課沒有講次。</span>';
  } catch (e) {
    host.innerHTML = `<span class="small muted">${escHtml(e.message)}</span>`;
  }
}

/**
 * Approve the checked chapters (this is the user's permission to generate them).
 * @returns {Promise<void>}
 */
async function startNoteSchedule() {
  const code = document.getElementById('nsCourse')?.value;
  const nos = [...document.querySelectorAll('.ns-pick:checked')].map(el => Number(el.value));
  if (!code || !nos.length) { showToast('請先選課程並勾選章節', 'error'); return; }
  const msg = `排程生成 ${nos.length} 章的 Gemini 筆記？\n\n會在背景依序進行，可隨時暫停；額度用完會等重置時間自動繼續。`;
  if (!(await askConfirm(msg, { okLabel: `開始排程 ${nos.length} 章` }))) return;
  try {
    const res = await _nsApi('/api/notes/schedule', { course_key: code, lecture_nos: nos });
    showToast(`已排入 ${res.added} 章${res.skipped ? `（${res.skipped} 章已在排程中）` : ''}`, 'success');
    await loadNoteSchedule();
    await loadNoteScheduleCandidates();
  } catch (e) {
    showToast('排程失敗：' + e.message, 'error');
  }
}

/**
 * Pause or resume the schedule depending on its current state.
 * @returns {Promise<void>}
 */
async function toggleNoteSchedulePause() {
  const paused = document.getElementById('nsPauseBtn')?.dataset.paused === '1';
  try {
    await _nsApi(paused ? '/api/notes/schedule/resume' : '/api/notes/schedule/pause', {});
    await loadNoteSchedule();
  } catch (e) {
    showToast('操作失敗：' + e.message, 'error');
  }
}

/**
 * Remove finished and failed chapters from the list.
 * @returns {Promise<void>}
 */
async function clearFinishedNoteSchedule() {
  try {
    const res = await _nsApi('/api/notes/schedule/clear-finished', {});
    showToast(`已清除 ${res.removed} 筆`, 'success');
    await loadNoteSchedule();
  } catch (e) {
    showToast('清除失敗：' + e.message, 'error');
  }
}

/**
 * Draw the schedule status line and item list.
 * @param {object} data Schedule status from the server
 */
function _nsRenderStatus(data) {
  const banner = document.getElementById('nsBanner');
  const pauseBtn = document.getElementById('nsPauseBtn');
  const items = data.items || [];
  if (pauseBtn) { pauseBtn.textContent = data.paused ? '繼續排程' : '暫停排程'; pauseBtn.dataset.paused = data.paused ? '1' : '0'; }
  if (banner) {
    banner.textContent = data.next_resume_at
      ? `Gemini 額度已滿，預計 ${fmtResumeTime(data.next_resume_at)} 繼續`
      : (data.paused ? '排程已暫停' : (items.some(i => ['pending', 'running'].includes(i.status)) ? '排程進行中' : ''));
  }
  const host = document.getElementById('nsItems');
  if (!host) return;
  host.innerHTML = items.map(i => {
    const extra = i.status === 'quota_wait' && i.resume_at ? `・預計 ${fmtResumeTime(i.resume_at)} 繼續` : (i.last_error && i.status === 'failed' ? `・${escHtml(i.last_error).slice(0, 80)}` : '');
    return `<div>${escHtml(i.course_key)} ${escHtml(i.chapter_id)} ${escHtml(i.chapter_title)}　<b>${_NS_STATUS[i.status] || escHtml(i.status)}</b>${extra}</div>`;
  }).join('') || '<span class="muted">目前沒有排程。</span>';
}

/**
 * Load (and lazily build) the 筆記排程 card.
 * @returns {Promise<void>}
 */
async function loadNoteSchedule() {
  const card = document.getElementById('noteScheduleCard');
  if (!card) return;
  try {
    if (card.dataset.ready !== '1') await _nsRenderSkeleton(card);
    _nsRenderStatus(await _nsApi('/api/notes/schedule'));
  } catch (e) {
    console.warn('Could not load note schedule:', e);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  loadNoteSchedule();
  setInterval(loadNoteSchedule, 15000);
});
