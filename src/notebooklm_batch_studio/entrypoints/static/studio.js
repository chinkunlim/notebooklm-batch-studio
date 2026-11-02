/* Gemini Notebook 學習工作室 — study and UX layer (loaded after studio-app.js).
   Toasts / confirm dialog, the overview built from the study plan, quiz review, explanations,
   mock-exam timer, spaced review, audio resume and the add-course wizard. Uses globals from
   studio-app.js (currentStudyCourse, activeStudyLectureNo, activeQuizVariant, currentQuizData,
   currentQuizAnswers, studyHistory, escHtml, lectureName, selectStudyLecture, loadQuizForChapter)
   and studio-shell.js (go, switchStudyTab, animateRings). */

/* ---------- Toasts and confirm dialog ---------- */
/**
 * Show a short non-blocking message in the corner.
 * @param {string} message Text to show
 * @param {string} type 'info' | 'success' | 'warning' | 'error'
 * @param {number} ms How long it stays, in milliseconds
 */
function showToast(message, type = 'info', ms = 4500) {
  let stack = document.getElementById('toastStack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toastStack';
    stack.setAttribute('role', 'status');
    stack.setAttribute('aria-live', 'polite');
    document.body.appendChild(stack);
  }
  const el = document.createElement('div');
  el.className = `note ${type}`;
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

/**
 * Ask the user to confirm an action in an in-page dialog (replaces window.confirm).
 * @param {string} message Question to show
 * @param {{okLabel?: string, danger?: boolean}} options Button label and danger styling
 * @returns {Promise<boolean>} True when the user confirms
 */
function askConfirm(message, { okLabel = '確定', danger = false } = {}) {
  return new Promise(resolve => {
    let overlay = document.getElementById('confirmOverlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'confirmOverlay';
      overlay.innerHTML = `<div id="confirmBox" role="dialog" aria-modal="true"><div id="confirmText"></div>
        <div class="actions"><button id="confirmCancel" class="btn btn-ghost">取消</button><button id="confirmOk" class="btn btn-primary">確定</button></div></div>`;
      document.body.appendChild(overlay);
    }
    document.getElementById('confirmText').textContent = message;
    const ok = document.getElementById('confirmOk');
    ok.textContent = okLabel;
    ok.className = danger ? 'btn btn-danger' : 'btn btn-primary';
    const close = result => { overlay.style.display = 'none'; resolve(result); };
    ok.onclick = () => close(true);
    document.getElementById('confirmCancel').onclick = () => close(false);
    overlay.onclick = e => { if (e.target === overlay) close(false); };
    overlay.style.display = 'flex';
    ok.focus();
  });
}

/* ---------- 研讀總覽: built from the study plan ---------- */
let currentPlan = null;
/**
 * A label without its leading emoji (the server's step names start with one; v05 shows plain text).
 * @param {string} text Label from the server
 * @returns {string} Plain label
 */
function plainLabel(text) {
  return String(text || '').replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu, '').trim();
}
/** Which part of the learning cycle each step belongs to. */
const STEP_TAGS = { audio: '輸入', guide: '輸入', flashcards: '間隔' };

/**
 * Load the study plan and draw the overview: learning cycle, progress, exam countdown and the lecture route.
 * @returns {Promise<void>} Resolves when rendered
 */
async function loadTodayPanel() {
  if (!currentStudyCourse) return;
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/plan`);
    currentPlan = await res.json();
    if (!res.ok) throw new Error(currentPlan.detail || res.statusText);
  } catch (e) {
    document.getElementById('todaySteps').innerHTML = `<li class="small muted">讀不到學習計畫：${escHtml(e.message)}</li>`;
    return;
  }
  renderCycle(currentPlan);
  renderMastery(currentPlan);
  renderExamBox(currentPlan);
  renderRoute(currentPlan);
  examReminder(currentPlan);
  if (typeof animateRings === 'function') animateRings(document.getElementById('view-overview'));
}

/**
 * 學習循環: the steps of the next lecture to study, then today's reviews.
 * @param {object} p Study plan
 */
function renderCycle(p) {
  const tick = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  const focus = p.lectures.find(l => p.next && l.lecture_no === p.next.lecture_no) || p.lectures[0];
  const steps = focus ? focus.steps.filter(st => st.available) : [];
  const dueCards = p.due.flashcards, dueMistakes = p.due.mistakes;
  document.getElementById('todaySteps').innerHTML = (focus ? `<li class="steps-head">${lectureName(focus.lecture_no)}　${escHtml(focus.topic)}</li>` : '') +
    steps.map(st => `<li class="${st.done ? 'done' : ''}" style="cursor:pointer" onclick="goToStep(${focus.lecture_no}, '${st.step}')"><span class="check">${tick}</span><span class="step-text">${escHtml(plainLabel(st.label))}</span><span class="tag">${STEP_TAGS[st.step] || '提取'}</span></li>`).join('') +
    `<li class="${dueCards ? '' : 'done'}" style="cursor:pointer" onclick="startReviewSession()"><span class="check">${tick}</span><span class="step-text">複習 ${dueCards} 張到期學習卡</span><span class="tag">間隔</span></li>` +
    (dueMistakes ? `<li style="cursor:pointer" onclick="switchStudyTab('mistakes')"><span class="check">${tick}</span><span class="step-text">看 ${dueMistakes} 題錯題</span><span class="tag warn">弱點</span></li>` : '') +
    (!steps.length && !p.next ? '<li class="small muted">這門課的步驟都完成了，做模擬考或複習錯題來檢查自己。</li>' : '');
}

/**
 * 掌握程度: overall progress, finished lectures and the last 7 days' quiz accuracy.
 * @param {object} p Study plan
 */
function renderMastery(p) {
  const n = p.lectures.length;
  const avg = n ? Math.round(p.lectures.reduce((a, l) => a + l.percent, 0) / n) : 0;
  document.getElementById('routeCourse').textContent = p.code;
  document.getElementById('masteryRing').dataset.p = avg;
  document.getElementById('masteryVal').textContent = `${avg}%`;
  document.getElementById('statDone').textContent = `${p.lectures.filter(l => l.percent >= 100).length} / ${n}`;
  const weekAgo = Date.now() - 7 * 86400000;
  const recent = (studyHistory || []).filter(h => h.total_questions && new Date(h.created_at).getTime() >= weekAgo);
  document.getElementById('statAcc').textContent = recent.length
    ? `${Math.round(recent.reduce((a, h) => a + h.score / h.total_questions, 0) / recent.length * 100)}%` : '—';
}

/**
 * What to focus on at this distance from the exam.
 * @param {number} days Days left
 * @returns {string} Advice
 */
function examTip(days) {
  if (days < 0) return '考試日期已過，可以改成下一次考試。';
  if (days === 0) return '今天考試：只看錯題和重點，相信自己。';
  if (days <= 1) return '明天考試：複習錯題與學習卡，早點休息。';
  if (days <= 7) return '最後一週：集中在錯題、到期學習卡和一回模擬考。';
  if (days <= 14) return '考前兩週：每天一回測驗，弱的章節先補。';
  if (days <= 30) return '考前一個月：開始全課複習，每週一次模擬考。';
  return '還有時間：照章節路線穩定前進，每天一點點。';
}

/**
 * 考試倒數 in the check-in card, or a date field to set the exam date right here.
 * @param {object} p Study plan
 */
function renderExamBox(p) {
  const box = document.getElementById('examBox');
  const line = document.getElementById('sprintLine');
  if (p.days_left === null) {
    box.innerHTML = `<span class="field-label">考試倒數</span>
      <p class="small muted" style="margin-bottom:8px">在這門課的設定填考試日期，研讀計畫與提醒會跟著倒數。</p>
      <button class="btn btn-soft btn-sm" onclick="openExamSetting()">到課程設定填寫</button>`;
    line.textContent = '今天先完成學習循環裡最重要的三件事。';
    return;
  }
  const d = Math.max(0, p.days_left), soon = p.days_left >= 0 && p.days_left <= 7;
  box.innerHTML = `<div class="exam ${soon ? 'soon' : ''}"><div class="exam-days"><b class="num">${d}</b><span>天後考試</span></div>
    <div style="min-width:0"><div class="small muted num">${escHtml(p.exam_date)}　<button class="link-btn" onclick="openExamSetting()">到課程設定修改</button></div>
    <div class="exam-tip">${escHtml(examTip(p.days_left))}</div></div></div>`;
  line.textContent = p.days_left < 0 ? examTip(p.days_left) : `距離考試還有 ${d} 天。${examTip(p.days_left)}`;
}

/**
 * Open this course's settings on 批次排程 with the 考試日期 field in view and highlighted
 * (the exam date is a course setting, so it is changed in one place only).
 */
function openExamSetting() {
  if (!currentStudyCourse) return;
  const code = currentStudyCourse.code;
  const already = activeCourseCode === code && document.querySelector('#detailOptions [data-opt="exam_date"]');
  activeCourseCode = code;  // so opening 批次排程 does not load another course first
  go('queue');
  setTimeout(() => {
    if (!already) viewCourseDetail(code);
    document.getElementById('detailOptionsBox').open = true;
    const t0 = Date.now();
    /** Check every 150 ms (up to 4 s) for the exam-date field, then scroll to it and highlight it. */
    const wait = () => {
      const field = document.querySelector('#detailOptions [data-opt="exam_date"]');
      if (!field) { if (Date.now() - t0 < 4000) setTimeout(wait, 150); return; }
      const label = field.closest('.opt-field');
      label.scrollIntoView({ behavior: 'smooth', block: 'center' });
      label.classList.add('flash-field');
      setTimeout(() => { label.classList.remove('flash-field'); field.focus({ preventScroll: true }); }, 900);
    };
    wait();
  }, 320);
}

/**
 * Once a day, remind about the exam when it is two weeks away or closer.
 * @param {object} p Study plan
 */
function examReminder(p) {
  if (p.days_left === null || p.days_left < 0 || p.days_left > 14) return;
  const key = `examNotice:${p.code}`, today = new Date().toDateString();
  if (prefLoad(key, '') === today) return;
  prefSave(key, today);
  showToast(`${p.days_left === 0 ? '今天考試' : `距離考試還有 ${p.days_left} 天`}。${examTip(p.days_left)}`, p.days_left <= 3 ? 'warning' : 'info', 9000);
}

/**
 * 章節路線: every lecture with its progress ring, steps (one click away) and a slot for memory strength.
 * @param {object} p Study plan
 */
function renderRoute(p) {
  const ring = n => `<span class="ring" data-p="${n}"><svg viewBox="0 0 44 44"><circle class="bg" cx="22" cy="22" r="19"/><circle class="fg" cx="22" cy="22" r="19"/></svg><b>${n}</b></span>`;
  document.getElementById('routeList').innerHTML = p.lectures.map(l => {
    const current = p.next && p.next.lecture_no === l.lecture_no;
    const tag = l.percent >= 100 ? '<span class="tag good">完成</span>' : current ? '<span class="tag">研讀中</span>' : l.percent > 0 ? '<span class="tag warn">進行中</span>' : '<span class="tag">未開始</span>';
    const chips = l.steps.map(st => {
      const cls = !st.available ? 'na' : (st.done ? 'done' : 'todo');
      const click = st.available ? `onclick="goToStep(${l.lecture_no}, '${st.step}')"` : 'disabled';
      return `<button class="step-chip ${cls}" ${click} title="${st.available ? (st.done ? '已完成' : '還沒做') : '尚未生成'}">${st.done ? '✓ ' : ''}${escHtml(plainLabel(st.label))}</button>`;
    }).join('');
    return `<div class="route-row ${current ? 'current' : ''}">${ring(l.percent)}
      <button class="route-title" onclick="selectStudyLecture(${l.lecture_no}); go('studio')"><span class="path-title">${escHtml(l.topic)}</span><span class="path-meta">${lectureName(l.lecture_no)}　·　完成 ${l.percent}%</span></button>
      <div class="step-chips">${chips}</div><div class="route-mem" data-mem="${l.lecture_no}"></div>${tag}</div>`;
  }).join('') || '<p class="small muted">這門課還沒有講次。</p>';
}

/**
 * Jump to the lecture and tab for one study step.
 * @param {number} lectureNo Lecture number
 * @param {string} step Step key such as 'audio', 'guide', 'quiz_1', 'flashcards'
 */
function goToStep(lectureNo, step) {
  const tab = { audio: 'audio', guide: 'reports', flashcards: 'flashcards' }[step] || 'quiz';
  selectStudyLecture(lectureNo);
  switchStudyTab(tab);
  if (tab === 'quiz') setTimeout(() => loadQuizForChapter(step), 300);
}

/**
 * Mark the current lecture's listening or reading step done (or undone).
 * @param {string} step 'audio' or 'guide'
 * @param {boolean} done True to mark done
 * @returns {Promise<void>} Resolves after saving
 */
async function markStep(step, done = true) {
  if (!currentStudyCourse || activeStudyLectureNo === null) return;
  const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/progress`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lecture_no: activeStudyLectureNo, step, done }),
  });
  if (res.ok) { showToast(done ? '已記錄完成，下一步會出現在「研讀總覽」' : '已取消完成標記', 'success'); loadTodayPanel(); }
  else showToast('記錄失敗', 'error');
}

/* ---------- Quiz: results, retry wrong only, explanations, mock-exam timer ---------- */
let lastWrongIndexes = [];
let mockTimer = null;

/**
 * Return the questions of the quiz currently shown.
 * @returns {Array<object>} Quiz questions
 */
function quizQuestions() {
  return (currentQuizData.quiz && currentQuizData.quiz.questions) || (currentQuizData.json_data && currentQuizData.json_data.questions) || [];
}

/**
 * Show the in-page result after submitting: score, per-chapter breakdown, verdict and 'why?' per question.
 * @param {number} score Correct answers
 * @param {number} total Question count
 * @param {Array<number>} wrong Indexes of wrong answers
 */
async function renderQuizResult(score, total, wrong) {
  await loadSavedExplanations();
  stopMockTimer();
  const pct = Math.round((score / total) * 100);
  lastWrongIndexes = wrong;
  const questions = quizQuestions();
  // Per-chapter breakdown when questions carry a chapter tag (course-wide exams).
  const byChapter = {};
  questions.forEach((q, i) => {
    const tag = /^(Ch|L)\d+$/i.test(q.source || '') ? q.source : null;
    if (!tag) return;
    byChapter[tag] = byChapter[tag] || { ok: 0, all: 0 };
    byChapter[tag].all += 1;
    if (!wrong.includes(i)) byChapter[tag].ok += 1;
  });
  const chapters = Object.entries(byChapter).sort();
  const breakdown = chapters.length ? `<div class="small" style="margin-top:10px">各章答對率　${chapters.map(([c, v]) => {
    const r = Math.round(100 * v.ok / v.all);
    return `<span class="badge ${r < 60 ? 'badge-danger' : r < 80 ? 'badge-warning' : 'badge-success'}" style="margin:2px;">${escHtml(c)} ${r}%</span>`;
  }).join('')}</div>` : '';
  const message = pct >= 90 ? '很穩！可以往下一個難度走。' : pct >= 70 ? '不錯，把錯的幾題弄懂就更穩了。' : '先看每題解析，再「只重做錯題」一次。';
  const box = document.createElement('div');
  box.className = 'result-card';
  box.id = 'quizResultCard';
  box.innerHTML = `<div class="row" style="justify-content:space-between;flex-wrap:wrap;align-items:flex-start">
      <div><div class="score">${score} / ${total}（${pct}%）</div><div class="muted">${message}</div>${breakdown}</div>
      <div class="row" style="flex-wrap:wrap;gap:8px">
        ${wrong.length ? `<button class="btn btn-primary" onclick="retryWrongOnly()">只重做錯的 ${wrong.length} 題</button>` : ''}
        <button class="btn btn-ghost" onclick="loadQuizForChapter(activeQuizVariant)">整份重做</button>
        ${wrong.length ? `<button class="btn btn-soft" onclick="switchStudyTab('mistakes')">看弱點複習</button>` : ''}
      </div></div>`;
  const container = document.getElementById('quizContainer');
  container.prepend(box);
  // Peak-end summary and confidence feedback (studio-learning.js).
  if (typeof decorateQuizResult === 'function') decorateQuizResult(box, score, total, wrong);
  // Verdict and "why?" on every question; lock the choices.
  questions.forEach((q, i) => {
    const title = document.querySelector(`#explanation-${i}`)?.parentElement?.firstElementChild;
    if (title && !title.querySelector('.verdict')) {
      title.insertAdjacentHTML('beforeend', wrong.includes(i) ? '<span class="verdict bad">✗ 答錯</span>' : '<span class="verdict ok">✓ 答對</span>');
    }
    const exp = document.getElementById(`explanation-${i}`);
    if (exp && !exp.querySelector('.why-btn, .explain-box')) {
      exp.insertAdjacentHTML('beforeend', explanationSlot(q.question, `explainQuestion(${i}, this)`, `explainQuestion(${i}, this, true)`));
    }
    document.querySelectorAll(`[id^="choice-${i}-"]`).forEach(el => el.classList.add('locked'));
  });
  document.getElementById('quizActionBar').style.display = 'none';
  box.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Re-render the quiz with only the questions answered wrong last time.
 */
function retryWrongOnly() {
  const questions = quizQuestions();
  const subset = lastWrongIndexes.map(i => questions[i]).filter(Boolean);
  if (!subset.length) return;
  const quiz = { ...(currentQuizData.quiz || currentQuizData.json_data), questions: subset };
  currentQuizData = { ...currentQuizData, quiz, json_data: quiz };
  renderQuizQuestions(quiz, activeQuizVariant);
  showToast(`只重做錯的 ${subset.length} 題`, 'info');
}

let savedExplanations = new Map();

/**
 * Load the explanations already saved for this course, keyed by question text.
 * @returns {Promise<Map<string, object>>} Question text to saved explanation
 */
async function loadSavedExplanations() {
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/explanations`);
    const items = res.ok ? await res.json() : [];
    savedExplanations = new Map(items.map(i => [String(i.question || '').trim(), i]));
  } catch (e) {
    savedExplanations = new Map();
  }
  return savedExplanations;
}

/**
 * HTML for an explanation box with its source label and an "ask again" button.
 * @param {string} html Rendered explanation (escaped and rendered by the server)
 * @param {string} savedAt ISO time it was saved
 * @param {string} askAgain JavaScript to run for "ask again"
 * @returns {string} Box HTML
 */
function explanationBox(html, savedAt, askAgain) {
  const when = savedAt ? new Date(savedAt).toLocaleString('zh-TW', { dateStyle: 'short', timeStyle: 'short' }) : '';
  return `<div class="explain-box"><div class="explain-head">Gemini Notebook 解釋${when ? `（已儲存 ${escHtml(when)}）` : ''}
    <button class="link-btn" onclick="${askAgain}">重新問</button></div>${html}</div>`;
}

/**
 * Ask Gemini Notebook (or reuse the saved answer) why a question's answer is correct, and show it.
 * @param {{question: string, choices: Array, answer_index: number, lecture_no: (number|null)}} q Question
 * @param {HTMLElement} anchor Element to put the explanation after (replaced when it is a button)
 * @param {boolean} force Ask again even if an explanation is saved
 * @param {string} askAgain JavaScript for the "ask again" button
 * @returns {Promise<void>} Resolves when shown or failed
 */
async function askExplanation(q, anchor, force, askAgain) {
  const original = anchor.textContent;
  if (anchor.tagName === 'BUTTON') { anchor.disabled = true; anchor.textContent = 'Gemini Notebook 回答中…'; }
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/explain`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lecture_no: q.lecture_no,
        question: q.question,
        choices: (q.choices || []).map(c => (c.text !== undefined ? c.text : c)),
        answer_index: q.answer_index,
        force,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    savedExplanations.set(q.question.trim(), { answer_md: data.answer, html: data.html, created_at: data.saved_at });
    const box = explanationBox(data.html || escHtml(data.answer), data.saved_at, askAgain);
    const holder = anchor.closest('.explain-box') || anchor;
    holder.insertAdjacentHTML('afterend', box);
    holder.remove();
    if (!data.from_cache) showToast('已向 Gemini Notebook 詢問並儲存，下次直接顯示', 'success', 2500);
  } catch (e) {
    if (anchor.tagName === 'BUTTON') { anchor.disabled = false; anchor.textContent = original; }
    showToast('Gemini Notebook 沒有回應：' + e.message, 'error');
  }
}

/**
 * Explain one question of the quiz on screen.
 * @param {number} index Question index
 * @param {HTMLElement} anchor Button or explanation box to replace
 * @param {boolean} force Ask again even if saved
 * @returns {Promise<void>} Resolves when shown
 */
function explainQuestion(index, anchor, force = false) {
  const q = quizQuestions()[index];
  if (!q) return Promise.resolve();
  return askExplanation({ ...q, lecture_no: activeStudyLectureNo }, anchor, force, `explainQuestion(${index}, this, true)`);
}

/**
 * Explain one question from the mistake notebook.
 * @param {string} mistakeId Mistake id
 * @param {HTMLElement} anchor Button or explanation box to replace
 * @param {boolean} force Ask again even if saved
 * @returns {Promise<void>} Resolves when shown
 */
function explainMistake(mistakeId, anchor, force = false) {
  const m = (window.currentMistakes || []).find(x => x.id === mistakeId);
  if (!m) return Promise.resolve();
  const q = { question: m.question_text, choices: m.choices, answer_index: m.correct_index, lecture_no: m.lecture_no };
  return askExplanation(q, anchor, force, `explainMistake('${mistakeId}', this, true)`);
}

/**
 * Explanation area for a question: the saved explanation, or a "why?" button.
 * @param {string} question Question text
 * @param {string} askJs JavaScript (with `this`) that asks for it
 * @param {string} askAgainJs JavaScript that asks again
 * @returns {string} HTML
 */
function explanationSlot(question, askJs, askAgainJs) {
  const saved = savedExplanations.get(String(question).trim());
  if (saved) return explanationBox(saved.html || escHtml(saved.answer_md || ''), saved.created_at, askAgainJs);
  return `<button class="btn btn-ghost btn-sm why-btn" onclick="${askJs}">為什麼？問 Gemini Notebook</button>`;
}

/**
 * Start the mock-exam countdown (1.5 minutes per question); submits automatically at zero.
 * @param {number} questionCount Number of questions
 */
function startMockTimer(questionCount) {
  stopMockTimer();
  let left = Math.round(questionCount * 1.5 * 60);  // 1.5 minutes per question
  const bar = document.getElementById('quizActionBar');
  let el = document.getElementById('mockTimer');
  if (!el) {
    el = document.createElement('span');
    el.id = 'mockTimer';
    el.className = 'timer';
    bar.prepend(el);
  }
  /** Update the countdown once a second; submit when time is up. */
  const tick = () => {
    const m = Math.floor(left / 60), s = left % 60;
    el.textContent = `剩 ${m}:${String(s).padStart(2, '0')}`;
    el.classList.toggle('low', left <= 300);
    if (left <= 0) { stopMockTimer(); showToast('時間到，自動交卷', 'warning'); submitQuizAttempt(); }
    left -= 1;
  };
  tick();
  mockTimer = setInterval(tick, 1000);
}

/**
 * Stop and remove the mock-exam countdown.
 */
function stopMockTimer() {
  if (mockTimer) clearInterval(mockTimer);
  mockTimer = null;
  document.getElementById('mockTimer')?.remove();
}

/* ---------- Spaced review: flashcards ---------- */
/**
 * Stable key for a flashcard (first 16 hex chars of SHA-256 of its front).
 * @param {string} text Card front
 * @returns {Promise<string>} Key
 */
async function cardKey(text) {
  const data = new TextEncoder().encode(text.trim());
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
}

/**
 * Save a spaced-review answer for one card and tell the student when it comes back.
 * @param {{front: string, back: string}} card The card
 * @param {boolean} remembered Whether it was recalled
 * @param {number|null} lectureNo Lecture number
 * @returns {Promise<void>} Resolves after saving
 */
async function rateCard(card, remembered, lectureNo) {
  const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/reviews`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind: 'flashcard', key: await cardKey(card.front), remembered, lecture_no: lectureNo,
      front: card.front, back: card.back }),
  });
  if (!res.ok) { showToast('記錄失敗', 'error'); return; }
  const data = await res.json();
  const days = [0, 1, 3, 7, 14, 30][data.stage] || 0;
  showToast(remembered ? `${days} 天後再複習` : '10 分鐘後會再出現', remembered ? 'success' : 'warning', 2200);
}

/**
 * Rate the card on screen and move to the next one.
 * @param {boolean} remembered Whether it was recalled
 * @returns {Promise<void>} Resolves after saving
 */
async function rateCurrentFlashcard(remembered) {
  const card = currentFlashcards[currentFlashcardIdx];
  if (!card) return;
  await rateCard(card, remembered, activeStudyLectureNo);
  if (currentFlashcardIdx < currentFlashcards.length - 1) nextFlashcard();
  else showToast('這一講的學習卡都看完了', 'success');
}

/* ---------- Audio: remember the position per course and lecture ---------- */
/**
 * Remember where the student stopped in an audio track and continue there next time (the track loads
 * with the page, so this happens quietly).
 * The speed is a global preference (設計與自訂 / the player), so only the position is stored here.
 * Calling it again for a new track replaces the previous track's listeners.
 * @param {HTMLAudioElement} audio The player
 * @param {string} key Storage key for this course and lecture
 */
function attachAudioResume(audio, key) {
  if (!audio) return;
  (audio._resume || []).forEach(([ev, fn]) => audio.removeEventListener(ev, fn));
  let saved = null;
  try { saved = JSON.parse(prefLoad(key, 'null')); } catch (e) { saved = null; }
  let last = 0;
  /** Restore the saved position once the track's length is known. */
  const restore = () => {
    if (saved && saved.t > 5 && saved.t < audio.duration - 5) {
      audio.currentTime = saved.t;  // silent: the player's clock already shows where it continues
    }
    audio.removeEventListener('loadedmetadata', restore);
  };
  /** Save the current position for this course and lecture. */
  const store = () => {
    prefSave(key, JSON.stringify({ t: Math.round(audio.currentTime), r: audio.playbackRate }));
  };
  /** Save at most every five seconds while playing. */
  const onTime = () => { if (Date.now() - last > 5000) { last = Date.now(); store(); } };
  audio._resume = [['loadedmetadata', restore], ['timeupdate', onTime], ['pause', store]];
  audio._resume.forEach(([ev, fn]) => audio.addEventListener(ev, fn));
}

/* ---------- Add-course wizard ---------- */
let wizardStep = 1;
const WIZARD_LABELS = ['① 選資料夾', '② 選內容', '③ 設定', '④ 確認'];

/**
 * Show one step of the add-course wizard (a folder must be chosen before step 2).
 * @param {number} step Step 1-4
 */
function wizardGo(step) {
  if (step === 2 && !(document.getElementById('folderPaths').value || '').trim()) {
    showToast('請先選一個課程資料夾', 'warning');
    return;
  }
  wizardStep = Math.max(1, Math.min(4, step));
  document.querySelectorAll('#addModal [data-step]').forEach(el => {
    el.style.display = Number(el.dataset.step) === wizardStep ? '' : 'none';
  });
  document.getElementById('wizardSteps').innerHTML = WIZARD_LABELS.map((label, i) =>
    `<span class="${i + 1 === wizardStep ? 'active' : i + 1 < wizardStep ? 'done' : ''}">${label}</span>`).join('');
  document.getElementById('wizardBack').style.visibility = wizardStep > 1 ? 'visible' : 'hidden';
  document.getElementById('wizardNext').style.display = wizardStep < 4 ? '' : 'none';
  if (wizardStep === 4) previewFolders();
}

/* Every remaining alert() becomes a non-blocking toast; the type follows the message. */
window.alert = message => {
  const text = String(message);
  const type = /失敗|錯誤|error/i.test(text) ? 'error' : /✅|成功|已/.test(text) ? 'success' : 'info';
  showToast(text, type);
};
