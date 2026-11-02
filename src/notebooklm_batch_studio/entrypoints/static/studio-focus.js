/* Gemini Notebook 學習工作室 — focus timer (Pomodoro): focus, short break, and a long break after a few rounds.
   Starting it makes a timer ring fly into the Dock, where it counts down as a ring or as digits (設計與自訂 →
   專注習慣). Habits (lengths, rounds, display, auto-start) are remembered preferences "pomo.*"; the 今日策略
   slider only changes today ("focusToday"). A running round survives a page reload ("pomo.state").
   Loaded after studio-shell.js (load, save, go, showToast, announce, handlers, persisted). */

const POMO_DEFAULTS = { focus: 25, short: 5, long: 15, rounds: 4 };
const POMO_ARC = 2 * Math.PI * 20;
/** Current round: phase focus | short | long; left / total in seconds; endAt (ms) while running. */
const pomo = { phase: 'focus', round: 1, left: 0, total: 0, running: false, endAt: 0, timer: 0 };
/** How the Dock shows the time: 'ring' (a ring counting down) or 'digits'. */
let pomoStyle = 'ring';

/**
 * A remembered habit in minutes (or rounds).
 * @param {string} key focus | short | long | rounds
 * @returns {number} Value
 */
function habit(key) {
  return parseInt(load(`pomo.${key}`, String(POMO_DEFAULTS[key])), 10) || POMO_DEFAULTS[key];
}

/**
 * Today's focus length: the 今日策略 value when it was set today, otherwise the habit.
 * @returns {number} Minutes
 */
function todayFocus() {
  try {
    const v = JSON.parse(load('focusToday', 'null'));
    if (v && v.date === new Date().toDateString()) return v.min;
  } catch (e) { /* not set today */ }
  return habit('focus');
}

/**
 * Length of a phase in seconds.
 * @param {string} phase focus | short | long
 * @returns {number} Seconds
 */
function phaseSeconds(phase) {
  return (phase === 'focus' ? todayFocus() : habit(phase)) * 60;
}

/**
 * mm:ss for a number of seconds.
 * @param {number} s Seconds
 * @returns {string} Text
 */
function clock(s) {
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

/** Remember the round so a reload continues it. */
function savePomo() {
  save('pomo.state', JSON.stringify({ phase: pomo.phase, round: pomo.round, left: pomo.left, total: pomo.total, running: pomo.running, endAt: pomo.endAt }));
}

/** Show the timer everywhere: Dock ring or digits, the control card, the start buttons and the tab title. */
function renderPomo() {
  const active = pomo.total > 0;
  const names = { focus: '專注', short: '短休息', long: '長休息' };
  $('#focusWrap').classList.toggle('show', active);
  $('#focusWrap').classList.toggle('break', pomo.phase !== 'focus');
  $('#focusWrap').classList.toggle('paused', active && !pomo.running);
  const p = active ? pomo.left / pomo.total : 1;
  $('#focusArc').style.strokeDashoffset = String(POMO_ARC * (1 - p));
  const digits = pomoStyle === 'digits';
  $('#focusWrap').classList.toggle('digits', digits);
  $('#dockFocusNum').textContent = digits ? clock(pomo.left) : String(Math.ceil(pomo.left / 60));
  $('#dockFocusLabel').textContent = `${names[pomo.phase]} ${clock(pomo.left)}`;
  $('#dockFocusTip').textContent = `${names[pomo.phase]}${pomo.running ? '' : '（暫停）'} ${clock(pomo.left)}`;
  $('#fpPhase').textContent = names[pomo.phase] + (active && !pomo.running ? '（暫停）' : '');
  $('#fpRound').textContent = `第 ${pomo.round} / ${habit('rounds')} 輪`;
  $('#fpTime').textContent = clock(pomo.left);
  $('#fpBar').style.width = `${(1 - p) * 100}%`;
  $('#fpToggle').textContent = pomo.running ? '暫停' : '開始';
  const next = pomo.phase !== 'focus' ? '接著：專注' : pomo.round >= habit('rounds') ? `接著：長休息 ${habit('long')} 分鐘` : `接著：短休息 ${habit('short')} 分鐘`;
  $('#fpNext').textContent = next;
  const idleLabel = `專注 ${todayFocus()}:00`;
  $('#btnPomodoro').textContent = active ? `${names[pomo.phase]} ${clock(pomo.left)}` : idleLabel;
  $('#btnFocusStart').textContent = active ? (pomo.running ? '暫停' : '繼續') : '開始專注';
  ['#btnPomodoro', '#btnFocusStart'].forEach(s => $(s).classList.toggle('running', pomo.running));
  document.title = pomo.running ? `${clock(pomo.left)} ${names[pomo.phase]} · Gemini Notebook 學習工作室` : 'Gemini Notebook 學習工作室';
}

/** One second passed: count down from the end time (stays right even when the tab sleeps). */
function pomoTick() {
  pomo.left = Math.max(0, Math.round((pomo.endAt - Date.now()) / 1000));
  if (pomo.left <= 0) { phaseDone(); return; }
  renderPomo();
}

/**
 * Run or pause the current phase.
 * @param {boolean} on True to run
 */
function setPomoRunning(on) {
  clearInterval(pomo.timer);
  pomo.running = on;
  if (on) { pomo.endAt = Date.now() + pomo.left * 1000; pomo.timer = setInterval(pomoTick, 1000); }
  savePomo(); renderPomo();
}

/**
 * Prepare a phase at its full length (not running yet).
 * @param {string} phase focus | short | long
 */
function setPhase(phase) {
  pomo.phase = phase;
  pomo.left = pomo.total = phaseSeconds(phase);
}

/** A phase ended: say so, move to the next phase, and start it when breaks run on their own. */
function phaseDone() {
  clearInterval(pomo.timer);
  pomo.running = false;
  const wasFocus = pomo.phase === 'focus';
  if (wasFocus) {
    const long = pomo.round >= habit('rounds');
    setPhase(long ? 'long' : 'short');
    showToast(long ? `完成 ${habit('rounds')} 輪專注，休息 ${habit('long')} 分鐘：走動一下、喝口水。` : `專注完成。休息 ${habit('short')} 分鐘：閉上眼睛，回想剛才學到的 3 個重點。`, 'success', 10000);
  } else {
    pomo.round = pomo.phase === 'long' ? 1 : pomo.round + 1;
    setPhase('focus');
    showToast('休息結束，準備好就開始下一輪專注。', 'info', 8000);
  }
  announce(wasFocus ? '專注完成，開始休息' : '休息結束');
  if (load('pomo.auto', 'false') === 'true' || wasFocus) setPomoRunning(true);
  else { savePomo(); renderPomo(); setFocusPop(true); }
}

/**
 * A timer ring flies from the button that started it into the Dock slot, along a soft curve.
 * @param {HTMLElement} from Button that started the timer
 */
function flyTimer(from) {
  const slot = $('#dockFocus'), a = from.getBoundingClientRect(), b = slot.getBoundingClientRect();
  if (lowMotion() || !a.width || !b.width) return;
  const chip = $('#focusRing').cloneNode(true);
  chip.removeAttribute('id'); chip.querySelectorAll('[id]').forEach(n => n.removeAttribute('id'));
  chip.classList.add('fly-timer');
  chip.style.cssText = `left:${b.left + b.width / 2 - 24}px;top:${b.top + b.height / 2 - 24}px;`;
  document.body.append(chip);
  const [x0, y0] = [a.left + a.width / 2 - (b.left + b.width / 2), a.top + a.height / 2 - (b.top + b.height / 2)];
  const frames = [];
  for (let i = 0; i <= 24; i++) {
    const t = i / 24, e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2, u = 1 - e;
    const lift = Math.sin(Math.PI * e) * 80;
    frames.push({ transform: `translate(${x0 * u}px, ${y0 * u - lift}px) scale(${1.3 - 0.3 * e})`, opacity: t < 0.08 ? t / 0.08 : 1 });
  }
  slot.style.visibility = 'hidden';
  chip.animate(frames, { duration: 900, easing: 'linear' }).onfinish = () => {
    chip.remove(); slot.style.visibility = '';
    slot.animate([{ transform: 'scale(1.12)' }, { transform: 'none' }], { duration: 360, easing: 'cubic-bezier(.22, 1, .36, 1)' });
  };
}

/**
 * Start (from idle), pause or continue the timer from a page button.
 * @param {HTMLElement} btn The button pressed
 */
function pomoButton(btn) {
  if (!pomo.total) {
    pomo.round = 1; setPhase('focus');
    setPomoRunning(true);
    requestAnimationFrame(() => flyTimer(btn));
    showToast(`開始專注 ${todayFocus()} 分鐘，計時收在左側欄`, 'success', 2600);
    return;
  }
  setPomoRunning(!pomo.running);
}

/**
 * Open or close the timer's control card next to the Dock.
 * @param {boolean} open True to open
 */
function setFocusPop(open) {
  $('#focusPop').classList.toggle('open', open);
  $('#dockFocus').setAttribute('aria-expanded', open);
}

/** Stop the timer completely (the Dock slot goes away). */
function stopPomo() {
  clearInterval(pomo.timer);
  Object.assign(pomo, { phase: 'focus', round: 1, left: 0, total: 0, running: false, endAt: 0 });
  forget('pomo.state'); setFocusPop(false); renderPomo();
}

/** Show the remembered habits in the 專注習慣 card. */
function applyFocusHabits() {
  $$('[data-habit]').forEach(r => { r.value = habit(r.dataset.habit); });
  $$('[data-habit-val]').forEach(b => { b.textContent = habit(b.dataset.habitVal); });
  renderPomo();
}

/** Continue a round that was running (or paused) before the page was reloaded. */
function restorePomo() {
  let st;
  try { st = JSON.parse(load('pomo.state', 'null')); } catch (e) { st = null; }
  if (!st || !st.total) { renderPomo(); return; }
  Object.assign(pomo, st, { timer: 0 });
  if (st.running) {
    pomo.left = Math.max(0, Math.round((st.endAt - Date.now()) / 1000));
    if (pomo.left <= 0) { phaseDone(); return; }
    setPomoRunning(true);
  } else renderPomo();
}

handlers.pomoStyle = v => { pomoStyle = v; renderPomo(); };
persisted.push('pomoStyle');
$('#btnFocusStart').addEventListener('click', e => pomoButton(e.currentTarget));
$('#btnPomodoro').addEventListener('click', e => pomoButton(e.currentTarget));
$('#dockFocus').addEventListener('click', e => { e.stopPropagation(); setFocusPop(!$('#focusPop').classList.contains('open')); });
document.addEventListener('click', e => { if (!e.target.closest('.dock-focus-wrap')) setFocusPop(false); });
$('#fpToggle').addEventListener('click', () => setPomoRunning(!pomo.running));
$('#fpPlus').addEventListener('click', () => { pomo.left += 300; pomo.total += 300; setPomoRunning(pomo.running); });
$('#fpSkip').addEventListener('click', () => { pomo.left = 0; pomo.endAt = Date.now(); phaseDone(); });
$('#fpStop').addEventListener('click', stopPomo);
$('#fpHabits').addEventListener('click', () => { setFocusPop(false); go('custom'); setTimeout(() => $('#habitCard').scrollIntoView({ behavior: 'smooth', block: 'center' }), 420); });
$$('[data-habit]').forEach(r => r.addEventListener('input', () => {
  save(`pomo.${r.dataset.habit}`, r.value);
  $(`[data-habit-val="${r.dataset.habit}"]`).textContent = r.value;
  if (r.dataset.habit === 'focus') applyTodayChoices();
  if (!pomo.running && pomo.left === pomo.total && pomo.total) setPhase(pomo.phase);
  renderPomo();
}));
