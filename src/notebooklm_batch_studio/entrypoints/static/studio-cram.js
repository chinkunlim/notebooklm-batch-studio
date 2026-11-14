/* Gemini Notebook 學習工作室 — Cramming Mode ("臨時抱佛腳"):
   1. Weak-first / red-yellow-green lecture switcher filter
   2. Multi-lecture scoped cram report & sprint quiz generation
   3. Cross-lecture unresolved mistakes + high-priority QA notes rapid review
   4. Time-budget pacing & 1.5x continuous audio playlist across selected lectures */

let cramModeActive = false;
let cramPackCache = null;
let cramAudioQueue = [];
let cramAudioHooked = false;

/**
 * Toggle Cramming Mode on/off, updating the lecture dropdown and cram panel.
 * @returns {Promise<void>} Resolves when cram pack is loaded if active
 */
async function toggleCramMode() {
  cramModeActive = !cramModeActive;
  const btn = document.getElementById('cramModeBtn');
  const panel = document.getElementById('cramPanel');
  if (btn) btn.classList.toggle('btn-primary', cramModeActive);
  if (panel) panel.hidden = !cramModeActive;
  if (cramModeActive) await refreshCramPack();
  else if (typeof syncStudyLectureSwitcher === 'function') syncStudyLectureSwitcher();
}

/**
 * Read checked lecture numbers from the cram lecture picker (empty = all).
 * @returns {Array<number>} Sorted selected lecture numbers
 */
function selectedCramLectures() {
  return [...document.querySelectorAll('.cram-lec-pick:checked')].map(el => Number(el.value)).sort((a, b) => a - b);
}

/**
 * Fetch GET /api/courses/{code}/study/cram-pack and render panel + ranked dropdown.
 * @returns {Promise<void>} Resolves when rendered
 */
async function refreshCramPack() {
  const course = typeof currentStudyCourse !== 'undefined' ? currentStudyCourse : null;
  if (!course) return;
  const lecs = selectedCramLectures();
  const hours = Number(document.getElementById('cramHoursInput')?.value) || 2;
  const qs = `hours=${encodeURIComponent(hours)}${lecs.length ? `&lectures=${lecs.join(',')}` : ''}`;
  try {
    const res = await fetch(`/api/courses/${course.code}/study/cram-pack?${qs}`);
    if (!res.ok) throw new Error(res.statusText);
    cramPackCache = await res.json();
    renderCramPanel(cramPackCache, lecs);
    applyCramLectureFilter(cramPackCache);
  } catch (err) {
    showToast(`載入考前急救包失敗：${err.message}`, 'error');
  }
}

/**
 * Re-populate #studyLectureSelect ordered by cram urgency with red/yellow/green badges.
 * @param {object} pack Cram pack payload
 * @returns {void}
 */
function applyCramLectureFilter(pack) {
  const select = document.getElementById('studyLectureSelect');
  if (!select || !cramModeActive) return;
  const onlyWeak = document.getElementById('cramOnlyWeakToggle')?.checked;
  const rows = (pack.lectures || []).filter(l => !onlyWeak || l.level !== 'strong');
  const opts = ['<option value="all">🔥 急救總覽</option>'];
  rows.forEach(l => {
    const icon = l.level === 'strong' ? '✅' : (l.mistake_count > 0 || (l.percent !== null && l.percent < 50) ? '🔴' : '🟡');
    const mem = l.percent === null ? '未練' : `${l.percent}%`;
    const err = l.mistake_count ? `・${l.mistake_count}錯` : '';
    opts.push(`<option value="${l.no}">${icon} L${pad2(l.no)} ${escHtml(l.topic)} (${mem}${err})</option>`);
  });
  select.innerHTML = opts.join('');
}

/**
 * Render the cramming control panel: pacing, lecture checkboxes, mistakes, and priority notes.
 * @param {object} pack Cram pack payload from backend
 * @param {Array<number>} checkedNos Previously checked lecture numbers
 * @returns {void}
 */
function renderCramPanel(pack, checkedNos) {
  const body = document.getElementById('cramPanelBody');
  if (!body) return;
  const exam = pack.days_until_exam !== null && pack.days_until_exam !== undefined
    ? `距離考試還有 <b>${pack.days_until_exam}</b> 天` : '未設考試日期';
  const checks = (pack.lectures || []).map(l => {
    const on = !checkedNos.length || checkedNos.includes(l.no) ? 'checked' : '';
    const icon = l.level === 'strong' ? '✅' : '⚠️';
    return `<label class="cbox"><input type="checkbox" class="cram-lec-pick" value="${l.no}" ${on} onchange="refreshCramPack()">${icon} L${pad2(l.no)} (${l.recommended_minutes}分)</label>`;
  }).join('');
  body.innerHTML = `<div class="small" style="margin-bottom:8px">${exam}・已按「低記憶＋多錯題」排好優先順序：</div>
    <div class="checks" style="margin-bottom:10px">${checks || '<span class="muted">尚無講次</span>'}</div>
    <div class="grid-2" style="gap:12px"><div>${renderCramMistakes(pack.mistakes || [])}</div>
    <div>${renderCramNotes(pack.high_priority_notes || [])}</div></div>`;
}

/**
 * Render cross-lecture unresolved mistakes list for rapid cram review.
 * @param {Array<object>} mistakes Unresolved mistakes across selected lectures
 * @returns {string} HTML string
 */
function renderCramMistakes(mistakes) {
  if (!mistakes.length) return '<p class="small muted">勾選章節目前沒有未解決錯題 🎉</p>';
  const items = mistakes.slice(0, 12).map(m => {
    const ans = m.choices && m.choices[m.correct_index] ? m.choices[m.correct_index] : `#${m.correct_index}`;
    return `<li style="margin-bottom:6px"><span class="badge">L${pad2(m.lecture_no || 0)}</span> ${escHtml(m.question_text)}
      <details class="small muted"><summary style="cursor:pointer">看正解</summary>${escHtml(ans)}</details></li>`;
  }).join('');
  return `<div class="field-label">🔥 未掌握錯題 (${mistakes.length})</div><ul class="small" style="padding-left:18px;margin:0">${items}</ul>`;
}

/**
 * Render high-priority QA notes across selected lectures.
 * @param {Array<object>} notes Saved QA notes sorted by importance
 * @returns {string} HTML string
 */
function renderCramNotes(notes) {
  if (!notes.length) return '<p class="small muted">勾選章節尚無高優先問答筆記。</p>';
  const items = notes.slice(0, 10).map(n => {
    const scope = n.lecture_no ? `L${pad2(n.lecture_no)}` : '全課';
    return `<li style="margin-bottom:6px"><span class="badge">${scope} ★${n.importance || 1}</span> <b>${escHtml(n.question || n.title || '')}</b>
      <div class="muted">${escHtml((n.answer_markdown || '').slice(0, 110))}…</div></li>`;
  }).join('');
  return `<div class="field-label">📌 重點問答筆記 (${notes.length})</div><ul class="small" style="padding-left:18px;margin:0">${items}</ul>`;
}

/**
 * Generate a scoped cram report or sprint quiz for the checked cram lectures.
 * @param {string} kind 'custom_report' or 'quiz'
 * @returns {Promise<void>} Resolves when generation request completes
 */
async function generateCramBundle(kind) {
  const course = typeof currentStudyCourse !== 'undefined' ? currentStudyCourse : null;
  if (!course || !cramPackCache) return;
  const picked = new Set(selectedCramLectures());
  const sids = (cramPackCache.lectures || [])
    .filter(l => (!picked.size || picked.has(l.no)) && l.source_id).map(l => l.source_id);
  if (!sids.length) { showToast('勾選的章節尚未上傳至 Gemini Notebook', 'error'); return; }
  const label = kind === 'quiz' ? '考前衝刺測驗' : '考前高頻重點濃縮報告';
  const prompt = kind === 'quiz'
    ? '針對以上章節出考前衝刺高頻考題，聚焦易混淆觀念與計算陷阱。'
    : '請彙整以上指定章節的考前必背定義、公式比較、常見陷阱與高頻考點速覽表。';
  if (typeof triggerScopedGenerate === 'function') {
    showToast(`正在生成「${label}」…`, 'info', 2000);
    await triggerScopedGenerate(course.code, kind, sids, prompt);
  }
}

/**
 * Queue and play audio overviews at 1.5x speed across selected cram lectures.
 * @returns {void}
 */
function playCramAudioQueue() {
  const course = typeof currentStudyCourse !== 'undefined' ? currentStudyCourse : null;
  const audioEl = document.getElementById('portalAudio');
  if (!course || !audioEl || !cramPackCache) return;
  const picked = new Set(selectedCramLectures());
  const targets = (cramPackCache.lectures || []).filter(l => !picked.size || picked.has(l.no)).map(l => l.no);
  const jobs = (course.jobs || []).filter(j => j.artifact_type === 'audio' && j.status === 'done' && j.output_path);
  cramAudioQueue = targets.map(no => jobs.find(j => j.lecture_no === no)).filter(Boolean);
  if (!cramAudioQueue.length) { showToast('勾選的章節目前沒有已完成的語音摘要', 'info'); return; }
  if (!cramAudioHooked) {
    cramAudioHooked = true;
    audioEl.addEventListener('ended', () => { if (cramAudioQueue.length) playNextCramAudio(course.code, audioEl); });
  }
  playNextCramAudio(course.code, audioEl);
}

/**
 * Pop and play the next audio job in cramAudioQueue at 1.5x playback speed.
 * @param {string} code Course code
 * @param {HTMLAudioElement} audioEl Portal audio element
 * @returns {void}
 */
function playNextCramAudio(code, audioEl) {
  const job = cramAudioQueue.shift();
  if (!job) return;
  audioEl.src = `/api/artifacts/${code}/download/${encodeURIComponent(job.output_path)}`;
  audioEl.playbackRate = 1.5;
  audioEl.play().catch(() => {});
  showToast(`🎧 1.5× 急救連播：L${pad2(job.lecture_no || 0)}（剩餘 ${cramAudioQueue.length} 講）`, 'info', 2400);
}

/**
 * Toggle visual layout guide outlines across the app (Cmd/Ctrl+Shift+G).
 * @returns {void}
 */
function toggleLayoutGuides() {
  const app = document.getElementById('app');
  if (!app) return;
  const on = app.classList.toggle('layout-guides');
  document.getElementById('btnLayoutGuides')?.classList.toggle('on', on);
  let hud = document.getElementById('layoutGuideHud');
  if (!hud) {
    hud = document.createElement('div');
    hud.id = 'layoutGuideHud';
    hud.className = 'layout-guide-hud';
    app.appendChild(hud);
  }
  const mode = document.querySelector('.seg[data-seg="layout"] .on')?.textContent || '—';
  hud.innerHTML = `<span>📐 參考線：<b>藍</b>側欄 <b>紅</b>頂欄/分隔線 <b>橘</b>工具列/急救 <b>紫</b>雙欄 <b>青</b>卡片 <b>綠</b>PDF</span>
    <span>版型：${escHtml(mode)} (${window.innerWidth}×${window.innerHeight})</span>
    <button type="button" class="btn btn-ghost btn-sm" style="color:#fff;padding:1px 8px" onclick="toggleLayoutGuides()">關閉</button>`;
}

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'g') {
    e.preventDefault();
    toggleLayoutGuides();
  }
});
