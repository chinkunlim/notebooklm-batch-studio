/* Gemini Notebook 學習工作室 — learning-psychology layer for the study portal.
   - Forgetting curve: memory strength per lecture on "今天", weakest first (spacing).
   - Habit: study streak and a 4-week heatmap (goal gradient, habit formation).
   - Zeigarnik effect: "上次停在…" card that resumes unfinished work.
   - Metacognition: rate confidence before answering; "sure but wrong" questions are flagged.
   - Interleaving: mixed review across lectures.  Generation effect: hide choices / write before flipping.
   - Peak-end: a result summary that compares with the last attempt.  Pomodoro focus timer.
   - Socratic tutor (Gemini Notebook chat that guides with questions).
   Uses globals from index.html / studio.js: currentStudyCourse, activeStudyLectureNo, activeQuizVariant,
   currentQuizData, escHtml, showToast, selectStudyLecture, switchStudyTab, loadQuizForChapter,
   renderQuizQuestions, quizQuestions, loadTodayPanel, loadFlashcardsViewer, selectChoice. */

/* ---------- Helpers ---------- */
/**
 * Build a course API URL.
 * @param {string} path Path after /api/courses/<code>
 * @returns {string} URL
 */
function courseApi(path) {
  return `/api/courses/${encodeURIComponent(currentStudyCourse.code)}${path}`;
}

/**
 * Two-digit lecture label, e.g. "L03".
 * @param {number|null} no Lecture number
 * @returns {string} Label
 */
function lecLabel(no) {
  return no === null || no === undefined ? '全課' : `L${String(no).padStart(2, '0')}`;
}

/* ---------- Zeigarnik: remember where the student stopped ---------- */
/**
 * Remember the current place (course, lecture, tab, quiz, answered count) in this browser.
 * @param {object} extra Fields to merge, e.g. {tab: 'quiz'} or {answered: 12}
 */
function rememberPlace(extra) {
  if (!currentStudyCourse) return;
  try {
    const key = `studioPlace:${currentStudyCourse.code}`;
    const prev = JSON.parse(localStorage.getItem(key) || '{}');
    const place = { ...prev, lecture: activeStudyLectureNo, variant: activeQuizVariant, at: Date.now() };
    // The answered count belongs to one quiz: drop it when the lecture, quiz or tab changes.
    if (prev.lecture !== place.lecture || prev.variant !== place.variant || (extra.tab && extra.tab !== 'quiz')) {
      delete place.answered;
    }
    Object.assign(place, extra);
    localStorage.setItem(key, JSON.stringify(place));
  } catch (e) { /* storage blocked: nothing to remember */ }
}

/**
 * Read the remembered place for the current course.
 * @returns {object|null} Saved place or null
 */
function savedPlace() {
  try {
    return JSON.parse(localStorage.getItem(`studioPlace:${currentStudyCourse.code}`) || 'null');
  } catch (e) {
    return null;
  }
}

/** Tab names shown in the resume card. */
const TAB_NAMES = { reader: '📄 課件', audio: '🎧 語音', quiz: '📝 測驗', mistakes: '📕 錯題', flashcards: '🗂️ 閃卡', reports: '📑 報告', tutor: '🧑‍🏫 家教' };

/**
 * Resume the remembered place.
 */
function resumePlace() {
  const place = savedPlace();
  if (!place) return;
  selectStudyLecture(place.lecture ?? null);
  switchStudyTab(place.tab || 'quiz');
  if (place.tab === 'quiz' && place.variant) loadQuizForChapter(place.variant);
}

/* ---------- Forgetting curve, streak and heatmap on "今天" ---------- */
/**
 * Draw the memory panel (resume card, streak, heatmap, memory strength) under the study plan.
 * @returns {Promise<void>}
 */
async function renderMemoryPanel() {
  const box = document.getElementById('todayContainer');
  if (!box || !currentStudyCourse) return;
  let data;
  try {
    const res = await fetch(courseApi('/study/memory'));
    if (!res.ok) return;
    data = await res.json();
  } catch (e) {
    return;
  }
  const place = savedPlace();
  const placeTab = place && place.tab && place.tab !== 'today' ? place.tab : null;
  const resume = placeTab ? `<div class="plan-card resume-card">
      <div><h4>上次停在</h4><div class="big" style="font-size:1.05rem;">${lecLabel(place.lecture)}・${TAB_NAMES[placeTab] || placeTab}
      ${place.answered ? `（上次答到第 ${place.answered} 題）` : ''}</div></div>
      <button class="primary" onclick="resumePlace()">▶ 繼續</button></div>` : '';
  const levels = { strong: '穩固', fading: '開始遺忘', weak: '快忘了' };
  const practised = data.lectures.filter(l => l.percent !== null).sort((a, b) => a.percent - b.percent);
  const weakest = practised.find(l => l.level !== 'strong');
  const bars = data.lectures.map(l => l.percent === null
    ? `<div class="mem-row"><span>${lecLabel(l.no)}</span><div class="mem-bar"><span style="width:0"></span></div><span class="mem-val muted">還沒練習</span></div>`
    : `<div class="mem-row" title="距上次練習 ${l.days_since} 天"><span>${lecLabel(l.no)}</span>
         <div class="mem-bar ${l.level}"><span style="width:${l.percent}%"></span></div>
         <span class="mem-val ${l.level}">${l.percent}% ${levels[l.level]}</span></div>`).join('');
  const heat = data.heatmap.map(d => `<span class="heat h${Math.min(4, d.count === 0 ? 0 : Math.ceil(d.count / 2))}" title="${d.date}：${d.count} 次"></span>`).join('');
  const section = document.createElement('div');
  section.id = 'memoryPanel';
  section.innerHTML = `${resume}
    <div class="plan-grid memory-grid">
      <div class="plan-card"><h4>連續學習</h4><div class="big">🔥 ${data.streak} 天</div>
        <div class="muted small">${data.studied_today ? '今天已經學過了，保持下去！' : '今天做一點點就能延續紀錄。'}</div>
        <div class="heatmap" aria-label="最近四週的學習次數">${heat}</div></div>
      <div class="plan-card"><h4>記憶強度（遺忘曲線估計）</h4>${bars}
        ${weakest ? `<button class="primary" style="margin-top:8px;" onclick="selectStudyLecture(${weakest.no}); switchStudyTab('flashcards')">🧠 先複習 ${lecLabel(weakest.no)}（${weakest.percent}%）</button>` : ''}
        <div class="muted small" style="margin-top:6px;">每次答對或「記得」都會讓記憶更持久；久沒碰就會慢慢下降。</div></div>
    </div>`;
  document.getElementById('memoryPanel')?.remove();
  box.prepend(section);
}

/* ---------- Metacognition: confidence before answering ---------- */
/** Confidence per question index for the quiz on screen. */
window.quizConfidence = {};

/**
 * Add "很確定 / 不太確定 / 用猜的" buttons to every question card.
 */
function addConfidenceButtons() {
  window.quizConfidence = {};
  quizQuestions().forEach((q, i) => {
    const exp = document.getElementById(`explanation-${i}`);
    const card = exp && exp.parentElement;
    if (!card || card.querySelector('.confidence-row')) return;
    const row = document.createElement('div');
    row.className = 'confidence-row';
    row.innerHTML = '<span>作答前，你有多確定？</span>' +
      [['sure', '😎 很確定'], ['unsure', '🤔 不太確定'], ['guess', '🎲 用猜的']]
        .map(([v, label]) => `<button type="button" data-v="${v}" onclick="setConfidence(${i}, '${v}', this)">${label}</button>`).join('');
    exp.before(row);
  });
}

/**
 * Store the confidence for one question and highlight the chosen button.
 * @param {number} i Question index
 * @param {string} value 'sure' | 'unsure' | 'guess'
 * @param {HTMLElement} btn The clicked button
 */
function setConfidence(i, value, btn) {
  window.quizConfidence[i] = value;
  btn.parentElement.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === btn));
}

/**
 * Count the confidence ratings that matter for review.
 * @param {Array<number>} wrong Indexes answered wrong
 * @param {number} total Question count
 * @returns {object|null} {sure_wrong, guess_right, rated} or null when nothing was rated
 */
function confidenceSummary(wrong, total) {
  const rated = Object.keys(window.quizConfidence).length;
  if (!rated) return null;
  let sureWrong = 0;
  let guessRight = 0;
  for (let i = 0; i < total; i++) {
    const c = window.quizConfidence[i];
    if (c === 'sure' && wrong.includes(i)) sureWrong += 1;
    if (c === 'guess' && !wrong.includes(i)) guessRight += 1;
  }
  return { sure_wrong: sureWrong, guess_right: guessRight, rated };
}

/* ---------- Peak-end: a result that compares with last time ---------- */
let previousAttempt = null;

/**
 * Remember the last attempt of this quiz before a new one starts (for the comparison).
 * @returns {Promise<void>}
 */
async function loadPreviousAttempt() {
  previousAttempt = null;
  try {
    const lec = activeQuizVariant === 'mixed_review' ? '' : `?lecture_no=${activeStudyLectureNo ?? ''}`;
    const res = await fetch(courseApi(`/study/history${lec}`));
    if (!res.ok) return;
    const same = (await res.json()).filter(a => a.quiz_variant === activeQuizVariant);
    same.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    previousAttempt = same[0] || null;
  } catch (e) { /* no comparison */ }
}

/**
 * Add the comparison with last time and the confidence findings to the result card.
 * @param {HTMLElement} box Result card
 * @param {number} score Correct answers
 * @param {number} total Question count
 * @param {Array<number>} wrong Wrong indexes
 */
function decorateQuizResult(box, score, total, wrong) {
  const lines = [];
  if (previousAttempt && previousAttempt.total_questions === total) {
    const diff = score - previousAttempt.score;
    lines.push(diff > 0 ? `📈 比上次多對 ${diff} 題，進步看得見！` : diff === 0 ? '➖ 和上次一樣，把錯題弄懂就能往上走。' : `📉 比上次少對 ${-diff} 題，間隔一段時間再測很正常，這正是在練記憶。`);
  } else if (!previousAttempt) {
    lines.push('🎉 第一次完成這份測驗！明天再做一次，記得會更牢。');
  }
  const summary = confidenceSummary(wrong, total);
  const sureWrong = wrong.filter(i => window.quizConfidence[i] === 'sure');
  if (sureWrong.length) {
    lines.push(`⚠️ 有 ${sureWrong.length} 題你「很確定」卻答錯（第 ${sureWrong.map(i => i + 1).join('、')} 題）：這是最值得弄懂的誤解，看完解析印象會特別深。`);
  }
  if (summary && summary.guess_right) lines.push(`🎲 有 ${summary.guess_right} 題是猜對的，下次複習時別跳過。`);
  if (!lines.length) return;
  box.insertAdjacentHTML('beforeend', `<div class="result-notes">${lines.map(l => `<div>${escHtml(l)}</div>`).join('')}</div>`);
  previousAttempt = { score, total_questions: total };
}

/* ---------- Generation effect: hide the choices until the student has recalled ---------- */
let hideChoices = false;

/**
 * Turn "先回想再看選項" on or off and apply it to the quiz on screen.
 * @param {boolean} on True to hide choices
 */
function setHideChoices(on) {
  hideChoices = on;
  try { localStorage.setItem('studioHideChoices', on ? '1' : '0'); } catch (e) { /* ignore */ }
  applyHideChoices();
}

/**
 * Hide (or show) every question's choices behind a "show" button.
 */
function applyHideChoices() {
  quizQuestions().forEach((q, i) => {
    const first = document.getElementById(`choice-${i}-0`);
    const wrap = first && first.parentElement;
    if (!wrap) return;
    wrap.classList.toggle('choices-hidden', hideChoices);
    if (hideChoices && !wrap.previousElementSibling?.classList.contains('reveal-btn')) {
      wrap.insertAdjacentHTML('beforebegin', '<button type="button" class="reveal-btn" onclick="this.nextElementSibling.classList.remove(\'choices-hidden\'); this.remove();">🙈 先在心裡回答，再按這裡看選項</button>');
    }
    if (!hideChoices) wrap.previousElementSibling?.classList.contains('reveal-btn') && wrap.previousElementSibling.remove();
  });
}

/**
 * Put the quiz tools (mixed review, hide-choices switch) above the questions.
 */
function addQuizTools() {
  const bar = document.getElementById('quizKindButtons');
  if (!bar || bar.querySelector('.mixed-btn')) return;
  bar.insertAdjacentHTML('beforeend', `
    <button class="mixed-btn ${activeQuizVariant === 'mixed_review' ? 'primary' : ''}" onclick="startMixedReview()" title="從學過的各講隨機抽題（交錯練習）">🔀 混合複習</button>
    <label class="hide-toggle"><input type="checkbox" ${hideChoices ? 'checked' : ''} onchange="setHideChoices(this.checked)"> 先回想再看選項</label>`);
}

/* ---------- Interleaving: mixed review across lectures ---------- */
/**
 * Build a 20-question quiz from random questions of every lecture's quizzes and start it.
 * @returns {Promise<void>}
 */
async function startMixedReview() {
  const jobs = (currentStudyCourse.jobs || []).filter(j => j.status === 'done' && j.lecture_no !== null
    && /^quiz_\d$/.test(j.artifact_type) && j.output_file);
  if (!jobs.length) { showToast('還沒有任何一講的測驗可以混合。', 'warning'); return; }
  showToast('正在從各講抽題…', 'info', 2000);
  const pool = [];
  await Promise.all(jobs.map(async j => {
    const variant = j.output_file.split('/').pop().replace(/_quiz\.json$/, '');
    try {
      const res = await fetch(courseApi(`/lectures/${j.lecture_no}/quiz/${encodeURIComponent(variant)}?with_answers=true`));
      if (!res.ok) return;
      const data = await res.json();
      const qs = (data.quiz || data.json_data || {}).questions || [];
      qs.forEach(q => pool.push({ ...q, source: lecLabel(j.lecture_no) }));
    } catch (e) { /* skip this quiz */ }
  }));
  if (!pool.length) { showToast('抽不到題目。', 'warning'); return; }
  for (let i = pool.length - 1; i > 0; i--) { const k = Math.floor(Math.random() * (i + 1)); [pool[i], pool[k]] = [pool[k], pool[i]]; }
  const quiz = { title: '混合複習', questions: pool.slice(0, 20) };
  activeQuizVariant = 'mixed_review';
  currentQuizData = { quiz, json_data: quiz };
  document.getElementById('quizScoreHeader').textContent = '';
  document.querySelectorAll('#quizKindButtons button').forEach(b => b.classList.toggle('primary', b.classList.contains('mixed-btn')));
  renderQuizQuestions(quiz, 'mixed_review');
  showToast(`🔀 從 ${new Set(pool.map(q => q.source)).size} 講抽出 ${quiz.questions.length} 題，交卷後看各講答對率。`, 'success');
}

/* ---------- Pomodoro focus timer ---------- */
const pomodoro = { left: 25 * 60, timer: null };

/**
 * Start or pause the 25-minute focus timer.
 */
function togglePomodoro() {
  const btn = document.getElementById('btnPomodoro');
  if (pomodoro.timer) {
    clearInterval(pomodoro.timer);
    pomodoro.timer = null;
    btn.classList.remove('running');
    return;
  }
  btn.classList.add('running');
  pomodoro.timer = setInterval(() => {
    pomodoro.left -= 1;
    const m = String(Math.floor(pomodoro.left / 60)).padStart(2, '0');
    const s = String(pomodoro.left % 60).padStart(2, '0');
    btn.textContent = `🍅 ${m}:${s}`;
    if (pomodoro.left <= 0) {
      clearInterval(pomodoro.timer);
      pomodoro.timer = null;
      pomodoro.left = 25 * 60;
      btn.textContent = '🍅 25:00';
      btn.classList.remove('running');
      showToast('🍅 專注 25 分鐘完成！休息 5 分鐘：閉上眼睛，回想剛才學到的 3 個重點（回想比重讀更能記住）。', 'success', 12000);
    }
  }, 1000);
}

/**
 * Put the focus-timer button next to the study tabs.
 */
function addPomodoroButton() {
  const tabs = document.getElementById('btnTabToday')?.parentElement;
  if (!tabs || document.getElementById('btnPomodoro')) return;
  tabs.insertAdjacentHTML('beforeend', '<button id="btnPomodoro" class="study-tab-btn pomodoro" onclick="togglePomodoro()" title="25 分鐘專注計時（再按一次暫停）">🍅 25:00</button>');
}

/* ---------- Tutor ---------- */
/**
 * Show the tutor conversation for the selected lecture.
 * @returns {Promise<void>}
 */
async function loadTutor() {
  const box = document.getElementById('tutorContainer');
  if (!currentStudyCourse) return;
  const lec = activeStudyLectureNo;
  box.innerHTML = `
    <div class="tutor-head"><div><h3>🧑‍🏫 蘇格拉底家教 · ${lecLabel(lec)}</h3>
      <p class="muted small">家教不直接給答案，而是一步步用問題引導你想通（只根據這${lec === null ? '門課' : '一講'}的講義）。每則訊息會用到一次 Gemini Notebook 對話。</p></div>
      <button class="link-btn" onclick="clearTutor()">🗑 重新開始</button></div>
    <div id="tutorLog" class="tutor-log">載入中…</div>
    <div class="tutor-suggest">
      ${['考考我這一講最核心的概念', '我不懂這一講在說什麼，請從頭引導我', '幫我找出我可能誤解的地方'].map(t => `<button type="button" onclick="sendTutor('${t}')">${t}</button>`).join('')}
    </div>
    <form class="tutor-input" onsubmit="event.preventDefault(); sendTutor();">
      <textarea id="tutorText" rows="2" placeholder="輸入你的想法或問題（⌘↵ 送出）" onkeydown="if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); sendTutor(); }"></textarea>
      <button class="primary" type="submit" id="tutorSend">送出</button>
    </form>`;
  try {
    const res = await fetch(courseApi(`/study/tutor${lec === null ? '' : `?lecture_no=${lec}`}`));
    renderTutorLog(res.ok ? await res.json() : []);
  } catch (e) {
    renderTutorLog([]);
  }
}

/**
 * Draw the conversation bubbles.
 * @param {Array<object>} messages Messages with role, text and html
 */
function renderTutorLog(messages) {
  const log = document.getElementById('tutorLog');
  if (!log) return;
  log.innerHTML = messages.length ? messages.map(m => `<div class="bubble ${m.role}">${m.role === 'tutor' ? (m.html || escHtml(m.text)) : escHtml(m.text)}</div>`).join('')
    : '<div class="muted small">還沒有對話。可以點上面的建議開始，或直接說說你目前的理解。</div>';
  log.scrollTop = log.scrollHeight;
}

/**
 * Send a message to the tutor and show the reply.
 * @param {string} [preset] Suggested message to send instead of the text box
 * @returns {Promise<void>}
 */
async function sendTutor(preset) {
  const input = document.getElementById('tutorText');
  const text = (preset || input.value).trim();
  if (!text) return;
  const log = document.getElementById('tutorLog');
  if (log.querySelector('.muted')) log.innerHTML = '';
  log.insertAdjacentHTML('beforeend', `<div class="bubble student">${escHtml(text)}</div><div class="bubble tutor typing">家教正在思考…</div>`);
  log.scrollTop = log.scrollHeight;
  input.value = '';
  document.getElementById('tutorSend').disabled = true;
  try {
    const res = await fetch(courseApi('/study/tutor'), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lecture_no: activeStudyLectureNo, message: text }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    log.querySelector('.typing').outerHTML = `<div class="bubble tutor">${data.html || escHtml(data.text)}</div>`;
  } catch (e) {
    log.querySelector('.typing').outerHTML = `<div class="bubble tutor error">沒有回應：${escHtml(e.message)}</div>`;
  } finally {
    document.getElementById('tutorSend').disabled = false;
    log.scrollTop = log.scrollHeight;
  }
}

/**
 * Start the tutor conversation over (local copy only).
 * @returns {Promise<void>}
 */
async function clearTutor() {
  if (!(await askConfirm('清除這段家教對話，重新開始？', { okLabel: '清除' }))) return;
  const lec = activeStudyLectureNo;
  await fetch(courseApi(`/study/tutor${lec === null ? '' : `?lecture_no=${lec}`}`), { method: 'DELETE' });
  renderTutorLog([]);
}

/* ---------- Flashcards: write the answer before flipping ---------- */
/**
 * Add a "write your answer first" box above the flashcard.
 */
function addRecallBox() {
  const box = document.getElementById('flashcardsViewerContainer');
  if (!box || box.querySelector('.recall-box') || !box.querySelector('.flip-card-wrap')) return;
  box.insertAdjacentHTML('afterbegin', '<textarea class="recall-box" rows="2" placeholder="✍️ 先寫下（或在心裡說出）你的答案，再翻面對照：自己想出來的比直接看更記得住。"></textarea>');
}

/* ---------- Wire into the existing page ---------- */
/**
 * Wrap an existing global function so extra work runs after it.
 * @param {string} name Global function name
 * @param {function(...*): *} after Called with the same arguments after the original finishes
 */
function runAfter(name, after) {
  const original = window[name];
  if (typeof original !== 'function') return;
  window[name] = async function (...args) {
    const result = await original.apply(this, args);
    try { await after(...args); } catch (e) { console.warn(`${name} add-on failed`, e); }
    return result;
  };
}

document.addEventListener('DOMContentLoaded', () => {
  try { hideChoices = localStorage.getItem('studioHideChoices') === '1'; } catch (e) { hideChoices = false; }
  addPomodoroButton();
  runAfter('loadTodayPanel', renderMemoryPanel);
  runAfter('loadFlashcardsViewer', addRecallBox);
  runAfter('renderQuizQuestions', async () => {
    addQuizTools();
    addConfidenceButtons();
    applyHideChoices();
    await loadPreviousAttempt();
  });
  runAfter('selectChoice', () => rememberPlace({ tab: 'quiz', answered: Object.keys(currentQuizAnswers).length }));
  const loadQuiz = window.loadQuizForChapter;
  window.loadQuizForChapter = variant => (variant === 'mixed_review' ? startMixedReview() : loadQuiz(variant));
});
