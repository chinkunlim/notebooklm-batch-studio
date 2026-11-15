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
  const state = document.getElementById('cramModeState');
  const panel = document.getElementById('cramPanel');
  if (btn) {
    btn.classList.toggle('is-active', cramModeActive);
    btn.setAttribute('aria-pressed', String(cramModeActive));
  }
  if (state) state.textContent = cramModeActive ? 'ON' : 'OFF';
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
    if (!res.ok) throw new Error(res.statusText || `HTTP ${res.status}`);
    cramPackCache = await res.json();
    renderCramPanel(cramPackCache, lecs);
    applyCramLectureFilter(cramPackCache);
  } catch (err) {
    const body = document.getElementById('cramPanelBody');
    if (body) {
      body.innerHTML = `<div class="empty-state">無法載入考前急救包（${escHtml(err.message)}）` +
        `<br><button type="button" class="btn btn-soft btn-sm" onclick="refreshCramPack()">重新載入</button></div>`;
    }
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
  renderLecturePopover();
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

let layoutGuidesHooked = false;

/**
 * Build a concise selector label for a DOM element (tag#id.firstClass).
 * @param {Element} el Target DOM element
 * @returns {string} Readable element label
 */
function guideLabelFor(el) {
  const tag = el.tagName.toLowerCase();
  const id = el.id ? `#${el.id}` : '';
  const cls = typeof el.className === 'string'
    ? el.className.trim().split(/\s+/).filter(Boolean).slice(0, 2).map(c => `.${c}`).join('')
    : '';
  return `${tag}${id}${cls}`;
}

/**
 * Check whether an element belongs to the active page and is visibly rendered in the viewport.
 * @param {Element} el Candidate DOM element
 * @returns {boolean} True when visible on the active view
 */
function isGuideElementVisible(el) {
  if (el.closest('#layoutGuideHud,#layoutGuideLayer,.view:not(.on),[hidden],dialog:not([open]),.qa-drawer:not(.open),.focus-pop:not(.open),.speed-menu:not(.open)')) return false;
  if (el.closest('.cp-pop') && !el.closest('.course-pick.open')) return false;
  if (el.closest('.lec-pop') && !el.closest('.lec-pick.open')) return false;
  const st = getComputedStyle(el);
  if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity) < 0.05) return false;
  const r = el.getBoundingClientRect();
  return r.width > 6 && r.height > 6 && r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth;
}

/**
 * Render detailed bounding boxes and top-left element labels when Layout Guides are active.
 * @returns {void}
 */
function renderLayoutGuides() {
  const app = document.getElementById('app');
  if (!app || !app.classList.contains('layout-guides')) return;
  let layer = document.getElementById('layoutGuideLayer');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'layoutGuideLayer';
    layer.className = 'layout-guide-layer';
    app.appendChild(layer);
  }
  const sel = '.dock,.topbar,.subbar,.resizable,.col,.gutter,.card,#cramPanel,.seg,.study-lec-switch,.reader-bar,.split-stage-head,.panel-head,.reader-layout,#keyPointList,#readerPages,#splitStage,#reportContentContainer,.report-frame,#quizContainer,#quizPager,#quizActionBar,#flashcardsViewerContainer,#tutorContainer,#qaNotesContainer,.empty-state,button,select,input,.tile,.dock-btn';
  const els = [...document.querySelectorAll(sel)].filter(isGuideElementVisible);
  const colors = { button: '#db2777', select: '#9333ea', input: '#9333ea', aside: '#2563eb', header: '#e11d48', article: '#0284c7' };
  const placed = [];
  layer.innerHTML = els.map(el => {
    const r = el.getBoundingClientRect();
    const c = colors[el.tagName.toLowerCase()] || (el.classList.contains('gutter') ? '#e11d48' : '#0f766e');
    let ty = 0;
    while (placed.some(p => Math.abs(p.x - r.left) < 110 && Math.abs(p.y - (r.top + ty)) < 14)) ty += 14;
    placed.push({ x: r.left, y: r.top + ty });
    const label = guideLabelFor(el);
    return `<div class="lg-box" data-label="${escHtml(label)}" style="left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;border-color:${c}">
      <span class="lg-tag" style="background:${c};top:${ty}px">${escHtml(label)}</span></div>`;
  }).join('');
}

/**
 * Toggle visual layout guide outlines and element labels across the app (Cmd/Ctrl+Shift+G).
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
  hud.innerHTML = `<span>📐 參考線｜點擊任意框線即可複製名稱（${escHtml(mode)} ${window.innerWidth}×${window.innerHeight}）</span>
    <button type="button" class="btn btn-ghost btn-sm" style="color:#fff;padding:1px 8px" onclick="toggleLayoutGuides()">關閉</button>`;
  if (!layoutGuidesHooked) {
    layoutGuidesHooked = true;
    window.addEventListener('resize', () => requestAnimationFrame(renderLayoutGuides));
    document.addEventListener('scroll', () => requestAnimationFrame(renderLayoutGuides), true);
    document.addEventListener('click', copyGuideLabelAt, true);
    document.addEventListener('click', () => setTimeout(renderLayoutGuides, 80), true);
    document.addEventListener('mousemove', e => highlightGuideAt(e.clientX, e.clientY));
  }
  if (on) renderLayoutGuides();
}

/**
 * Highlight layout guide boxes whose bounds contain the pointer coordinates.
 * @param {number} x Viewport X coordinate
 * @param {number} y Viewport Y coordinate
 * @returns {void}
 */
function highlightGuideAt(x, y) {
  const layer = document.getElementById('layoutGuideLayer');
  if (!layer || !document.getElementById('app')?.classList.contains('layout-guides')) return;
  layer.querySelectorAll('.lg-box').forEach(box => {
    const r = box.getBoundingClientRect();
    box.classList.toggle('is-hover', x >= r.left && x <= r.right && y >= r.top && y <= r.bottom);
  });
}

/**
 * Copy the innermost layout guide box label at the clicked coordinates to clipboard.
 * @param {MouseEvent} e Click event
 * @returns {void}
 */
function copyGuideLabelAt(e) {
  const app = document.getElementById('app');
  const layer = document.getElementById('layoutGuideLayer');
  if (!app?.classList.contains('layout-guides') || !layer) return;
  if (e.target.closest('#layoutGuideHud, #btnLayoutGuides')) return;
  const hits = [...layer.querySelectorAll('.lg-box')].filter(box => {
    const r = box.getBoundingClientRect();
    return e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
  });
  if (!hits.length) return;
  hits.sort((a, b) => (a.offsetWidth * a.offsetHeight) - (b.offsetWidth * b.offsetHeight));
  const label = hits[0].dataset.label || '';
  if (!label) return;
  e.preventDefault();
  e.stopPropagation();
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(label).catch(() => {});
  showToast(`📋 已複製：${label}`, 'info', 2200);
}

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === 'g') {
    e.preventDefault();
    toggleLayoutGuides();
  }
});

/**
 * Sync the warm-paper custom lecture popover UI from #studyLectureSelect options.
 * @returns {void}
 */
function renderLecturePopover() {
  const select = document.getElementById('studyLectureSelect');
  const pop = document.getElementById('lecPop');
  const label = document.getElementById('lecPickLabel');
  if (!select || !pop || !label) return;
  const opts = [...select.options];
  const active = opts.find(o => o.value === select.value) || opts[0];
  label.textContent = active ? active.textContent : '選擇講次…';
  pop.innerHTML = opts.map(o => {
    const on = o.value === select.value ? ' on' : '';
    return `<button type="button" class="lec-pop-item${on}" role="option" aria-selected="${o.value === select.value}" data-val="${escHtml(o.value)}">${escHtml(o.textContent)}</button>`;
  }).join('');
  pop.querySelectorAll('.lec-pop-item').forEach(btn => {
    btn.addEventListener('click', () => {
      select.value = btn.dataset.val;
      document.getElementById('lecPick')?.classList.remove('open');
      document.getElementById('lecPickBtn')?.setAttribute('aria-expanded', 'false');
      renderLecturePopover();
      if (typeof jumpToStudyLecture === 'function') jumpToStudyLecture(select.value);
    });
  });
}

document.getElementById('lecPickBtn')?.addEventListener('click', e => {
  e.stopPropagation();
  const wrap = document.getElementById('lecPick');
  if (!wrap) return;
  const open = wrap.classList.toggle('open');
  e.currentTarget.setAttribute('aria-expanded', String(open));
});

document.addEventListener('click', e => {
  const wrap = document.getElementById('lecPick');
  if (wrap && !wrap.contains(e.target)) {
    wrap.classList.remove('open');
    document.getElementById('lecPickBtn')?.setAttribute('aria-expanded', 'false');
  }
});

// Prevent background page scrolling while lecture or course dropdown menu is open. (Handled by CSS overscroll-behavior: contain)

/**
 * Toggle collapse/expand of the study right column via the existing col-toggle button.
 * @returns {void}
 */
function toggleStudySideCollapse() {
  const tg = document.querySelector('#paneStudy > .col-resizer .col-toggle');
  if (tg) tg.click();
}

/**
 * Attach vertical collapse/expand chevron buttons to right-column study cards.
 * @returns {void}
 */
function initSideCardCollapses() {
  ['playerCard', 'sideInfo', 'bench', 'myCoursesCard', 'courseLecturesCard'].forEach(id => {
    const card = document.getElementById(id);
    const head = card && !card.dataset.collapseHooked && card.querySelector(':scope > .card-head, :scope > .player-controls, :scope > .bench-head');
    if (!head) return;
    card.dataset.collapseHooked = '1';
    const btn = Object.assign(document.createElement('button'), { type: 'button', className: 'card-collapse-btn', title: '收合 / 展開此區塊', innerHTML: '<i class="icon-chevron-up"></i>' });
    btn.setAttribute('aria-expanded', 'true');
    btn.addEventListener('click', () => {
      const collapsed = card.classList.toggle('is-collapsed');
      btn.setAttribute('aria-expanded', String(!collapsed));
      btn.innerHTML = collapsed ? '<i class="icon-chevron-down"></i>' : '<i class="icon-chevron-up"></i>';
    });
    const existingRow = head.querySelector(':scope > .card-title-row');
    const title = head.querySelector(':scope > h2, :scope > .h2');
    if (existingRow) existingRow.appendChild(btn);
    else if (id === 'bench' && title) {
      const row = Object.assign(document.createElement('div'), { className: 'card-title-row' });
      head.insertBefore(row, title); row.append(title, btn);
    } else head.appendChild(btn);
  });
}

/**
 * Dynamically size #paneStudy to fit available browser viewport height (adapts to Safari/Chrome bars and fullscreen).
 * @returns {void}
 */
function updateStudyViewportHeight() {
  const pane = document.getElementById('paneStudy');
  if (!pane || pane.hidden || (pane.dataset.layout !== 'split' && pane.dataset.layout !== 'stack')) return;
  const h = (window.visualViewport && window.visualViewport.height) || window.innerHeight;
  pane.style.setProperty('--study-h', `${Math.max(460, Math.floor(h - 24))}px`);
}

/**
 * Return true if an inner scroller under target can scroll further in direction dir (1=down, -1=up).
 * @param {EventTarget|null} target Wheel event target
 * @param {number} dir Scroll direction (1 or -1)
 * @returns {boolean}
 */
function canInnerScroll(target, dir) {
  const sel = '.kp-list.kp-all-mode, #readerPages, .bench-body, .bench-stage > .panel, .side-catalog-host, .study-side';
  for (let el = target instanceof Element ? target.closest(sel) : null; el; el = el.parentElement?.closest(sel) || null) {
    if (el.scrollHeight > el.clientHeight + 1 && (dir > 0 ? el.scrollTop + el.clientHeight < el.scrollHeight - 1 : el.scrollTop > 1)) return true;
  }
  return false;
}

/**
 * Scroll outer page down until #paneStudy sticks at 12px top margin before scrolling inner PDF/bench.
 * Clamps #paneStudy top at 12px across reader, side-column, and scrollbar scrolling while #view-studio.on.
 * @returns {void}
 */
function initStudyStickyWheel() {
  const pane = document.getElementById('paneStudy'), host = document.getElementById('app') || pane;
  if (!pane || !host || pane.dataset.stickyWheelHooked) return;
  pane.dataset.stickyWheelHooked = '1';
  host.addEventListener('wheel', e => {
    const target = pane.dataset.layout === 'split' ? pane : (pane.dataset.layout === 'stack' ? document.querySelector('#bench .bench-stage') : null);
    if (!target || !document.getElementById('view-studio')?.classList.contains('on') || pane.hidden || e.ctrlKey) return;
    if (document.querySelector('.lec-pop.open, .bm-pick.open')) return;
    if (e.target instanceof Element && e.target.closest('dialog[open], .qa-drawer.open, .focus-pop.open, .speed-menu.open, .disc-pop.open')) return;
    const top = target.getBoundingClientRect().top;
    if (e.deltaY > 0) {
      if (top > 13) { e.preventDefault(); window.scrollBy(0, Math.min(e.deltaY, top - 12)); }
      else if (!canInnerScroll(e.target, 1)) e.preventDefault();
      return;
    }
    if (e.deltaY < 0 && !canInnerScroll(e.target, -1) && window.scrollY > 0) { e.preventDefault(); window.scrollBy(0, e.deltaY); }
  }, { passive: false });
}

/**
 * Switch the right column of #paneStudy between study tools and course catalog without hiding #readerCard.
 * @param {string} v Target pane ('study' or 'courses')
 * @returns {void}
 */
function switchStudySidePane(v) {
  const mode = v || document.querySelector('[data-seg="studioPane"] .on')?.dataset.value || 'study';
  const study = document.getElementById('paneStudy'), courses = document.getElementById('paneCourses'), side = document.getElementById('studySide');
  let host = document.getElementById('sideCatalogHost');
  if (study && side && study.dataset.layout === 'split') {
    if (!host) { host = Object.assign(document.createElement('div'), { id: 'sideCatalogHost', className: 'side-catalog-host' }); side.appendChild(host); }
    if (courses && !host.children.length) Array.from(courses.children).forEach(ch => host.appendChild(ch));
    if (courses) courses.hidden = true;
    study.hidden = false;
    study.dataset.sideMode = mode;
    if (mode === 'courses' && study.classList.contains('side-collapsed')) study.querySelector(':scope > .col-resizer .col-toggle')?.click();
  } else {
    if (courses && host && host.children.length) Array.from(host.children).forEach(ch => courses.appendChild(ch));
    if (study) { delete study.dataset.sideMode; study.hidden = mode !== 'study'; }
    if (courses) courses.hidden = mode !== 'courses';
  }
  if (typeof updateMini === 'function') updateMini();
  if (typeof sizeCanvases === 'function') requestAnimationFrame(sizeCanvases);
}

initSideCardCollapses(); initStudyStickyWheel(); updateStudyViewportHeight();
['load', 'resize'].forEach(ev => window.addEventListener(ev, updateStudyViewportHeight));
window.visualViewport?.addEventListener('resize', updateStudyViewportHeight);
['fullscreenchange', 'webkitfullscreenchange'].forEach(ev => document.addEventListener(ev, () => { setTimeout(updateStudyViewportHeight, 60); setTimeout(updateStudyViewportHeight, 360); }));
document.addEventListener('click', () => setTimeout(updateStudyViewportHeight, 60));
const _studyPaneObs = document.getElementById('paneStudy');
if (_studyPaneObs && typeof MutationObserver === 'function') new MutationObserver(updateStudyViewportHeight).observe(_studyPaneObs, { attributes: true, attributeFilter: ['hidden', 'data-layout'] });
