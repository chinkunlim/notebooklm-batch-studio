/* Gemini Notebook 學習工作室 — study and UX layer (loaded after the inline script in index.html).
   Toasts / confirm dialog, theme, "today" plan, quiz review, explanations, mock-exam timer,
   spaced review, audio resume and the add-course wizard. Uses globals from index.html:
   currentStudyCourse, activeStudyLectureNo, activeQuizVariant, currentQuizData, currentQuizAnswers,
   escHtml, selectStudyLecture, switchStudyTab, loadQuizForChapter. */

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
  el.className = `toast ${type}`;
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
        <div class="actions"><button id="confirmCancel">取消</button><button id="confirmOk" class="primary">確定</button></div></div>`;
      document.body.appendChild(overlay);
    }
    document.getElementById('confirmText').textContent = message;
    const ok = document.getElementById('confirmOk');
    ok.textContent = okLabel;
    ok.className = danger ? 'btn-danger' : 'primary';
    const close = result => { overlay.style.display = 'none'; resolve(result); };
    ok.onclick = () => close(true);
    document.getElementById('confirmCancel').onclick = () => close(false);
    overlay.onclick = e => { if (e.target === overlay) close(false); };
    overlay.style.display = 'flex';
    ok.focus();
  });
}

/* ---------- Theme (dark / light; follows the system until chosen) ---------- */
/**
 * Apply the dark or light theme (or follow the system when none is chosen).
 * @param {string|null} theme 'dark', 'light' or null for the system setting
 */
function applyTheme(theme) {
  const root = document.documentElement;
  if (theme) root.setAttribute('data-theme', theme); else root.removeAttribute('data-theme');
  const light = theme ? theme === 'light' : window.matchMedia('(prefers-color-scheme: light)').matches;
  document.body.classList.toggle('theme-light', light);
  const btn = document.getElementById('btnTheme');
  if (btn) btn.textContent = light ? '🌙 深色' : '☀️ 淺色';
}

/**
 * Switch between dark and light themes and remember the choice in this browser.
 */
function toggleTheme() {
  const light = document.body.classList.contains('theme-light');
  const next = light ? 'dark' : 'light';
  try { localStorage.setItem('studioTheme', next); } catch (e) { /* storage blocked */ }
  applyTheme(next);
}

/* ---------- Today: plan, countdown, reviews ---------- */
let currentPlan = null;

/**
 * Load the study plan and render the Today tab: next step, exam countdown, reviews due, lecture progress.
 * @returns {Promise<void>} Resolves when rendered
 */
async function loadTodayPanel() {
  const box = document.getElementById('todayContainer');
  if (!box || !currentStudyCourse) return;
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/plan`);
    currentPlan = await res.json();
    if (!res.ok) throw new Error(currentPlan.detail || res.statusText);
  } catch (e) {
    box.innerHTML = `<div class="empty-state">讀不到學習計畫：${escHtml(e.message)}</div>`;
    return;
  }
  const p = currentPlan;
  const countdown = p.days_left === null
    ? `<div class="big">未設定</div><div style="font-size:0.8rem;color:var(--text-muted)">在管理控制台的「⚙️ 產出設定」填考試日期</div>`
    : `<div class="big">${p.days_left >= 0 ? p.days_left : 0} 天</div><div style="font-size:0.8rem;color:var(--text-muted)">${escHtml(p.exam_date)}${p.days_left < 0 ? '（已過）' : ''}</div>`;
  const next = p.next
    ? `<div class="big" style="font-size:1.15rem;">${escHtml(p.next.label)}</div>
       <div style="font-size:0.85rem;color:var(--text-muted);margin:4px 0 10px;">第 ${String(p.next.lecture_no).padStart(2, '0')} 講：${escHtml(p.next.topic)}</div>
       <button class="primary" onclick="goToStep(${p.next.lecture_no}, '${p.next.step}')">▶️ 開始</button>`
    : `<div class="big" style="font-size:1.15rem;">🎉 都完成了</div><div style="font-size:0.85rem;color:var(--text-muted)">做模擬考或複習錯題來檢查自己</div>`;
  const dueCards = p.due.flashcards, dueMistakes = p.due.mistakes;
  const reviews = `<div class="big">${dueCards + dueMistakes}</div>
    <div style="font-size:0.85rem;color:var(--text-muted);margin-bottom:10px;">閃卡 ${dueCards} 張・錯題 ${dueMistakes} 題</div>
    ${dueCards ? `<button onclick="startReviewSession()">🗂️ 複習到期閃卡</button>` : ''}
    ${dueMistakes ? `<button onclick="switchStudyTab('mistakes')">📕 看錯題</button>` : ''}`;
  const rows = p.lectures.map(lec => `
    <div class="chapter-row">
      <div><strong>第 ${String(lec.lecture_no).padStart(2, '0')} 講</strong><div style="font-size:0.8rem;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escHtml(lec.topic)}</div></div>
      <div class="step-chips">${lec.steps.map(s => {
        const cls = !s.available ? 'na' : (s.done ? 'done' : 'todo');
        const click = s.available ? `onclick="goToStep(${lec.lecture_no}, '${s.step}')"` : '';
        return `<button class="step-chip ${cls}" ${click} title="${s.available ? (s.done ? '已完成' : '還沒做') : '尚未生成'}">${s.done ? '✓ ' : ''}${escHtml(s.label)}</button>`;
      }).join('')}</div>
      <div style="min-width:90px;"><div class="meter" aria-label="進度 ${lec.percent}%"><span style="width:${lec.percent}%"></span></div><div style="font-size:0.75rem;text-align:right;color:var(--text-muted)">${lec.percent}%</div></div>
    </div>`).join('');
  box.innerHTML = `
    <div class="plan-grid">
      <div class="plan-card next"><h4>下一步</h4>${next}</div>
      <div class="plan-card"><h4>距離考試</h4>${countdown}</div>
      <div class="plan-card"><h4>今天要複習</h4>${reviews}</div>
    </div>
    <div class="plan-card"><h4>各講進度（點任一步驟直接前往）</h4>${rows}</div>`;
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
  if (res.ok) showToast(done ? '已記錄完成 ✓ 下一步會出現在「🏠 今天」' : '已取消完成標記', 'success');
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
  const breakdown = chapters.length ? `<div style="margin-top:10px;font-size:0.85rem;">各章答對率：${chapters.map(([c, v]) => {
    const r = Math.round(100 * v.ok / v.all);
    return `<span class="badge ${r < 60 ? 'badge-danger' : r < 80 ? 'badge-warning' : 'badge-success'}" style="margin:2px;">${escHtml(c)} ${r}%</span>`;
  }).join('')}</div>` : '';
  const message = pct >= 90 ? '很穩！可以往下一個難度走。' : pct >= 70 ? '不錯，把錯的幾題弄懂就更穩了。' : '先看每題解析，再「只重做錯題」一次。';
  const box = document.createElement('div');
  box.className = 'result-card';
  box.id = 'quizResultCard';
  box.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
      <div><div class="score">${score} / ${total}（${pct}%）</div><div style="color:var(--text-muted);">${message}</div>${breakdown}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;">
        ${wrong.length ? `<button class="primary" onclick="retryWrongOnly()">🔁 只重做錯的 ${wrong.length} 題</button>` : ''}
        <button onclick="loadQuizForChapter(activeQuizVariant)">↺ 整份重做</button>
        ${wrong.length ? `<button onclick="switchStudyTab('mistakes')">📕 錯題集</button>` : ''}
      </div></div>`;
  const container = document.getElementById('quizContainer');
  container.prepend(box);
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
  return `<div class="explain-box"><div class="explain-head">📖 Gemini Notebook 解釋${when ? `（已儲存 ${escHtml(when)}）` : ''}
    <button class="link-btn" onclick="${askAgain}">🔁 重新問</button></div>${html}</div>`;
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
  if (anchor.tagName === 'BUTTON') { anchor.disabled = true; anchor.textContent = '⏳ Gemini Notebook 回答中…'; }
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
  return `<button class="why-btn" style="margin-top:8px;font-size:0.8rem;" onclick="${askJs}">🤔 為什麼？問 Gemini Notebook</button>`;
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
    el.textContent = `⏱ ${m}:${String(s).padStart(2, '0')}`;
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
  showToast(remembered ? `👍 ${days} 天後再複習` : '🔁 10 分鐘後會再出現', remembered ? 'success' : 'warning', 2200);
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
  else showToast('這一講的閃卡都看完了 🎉', 'success');
}

/**
 * Open the flashcards that are due now as a review session.
 * @returns {Promise<void>} Resolves when started
 */
async function startReviewSession() {
  const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/reviews/due`);
  const due = res.ok ? await res.json() : [];
  if (!due.length) { showToast('目前沒有到期的閃卡 👍', 'success'); return; }
  switchStudyTab('flashcards');
  setTimeout(() => {
    currentFlashcards = due.filter(d => d.kind === 'flashcard').map(d => ({ front: d.front, back: d.back, lecture_no: d.lecture_no }));
    currentFlashcardIdx = 0;
    renderCurrentFlashcard();
    showToast(`開始複習 ${currentFlashcards.length} 張到期閃卡`, 'info');
  }, 400);
}

/* ---------- Audio: remember position and speed ---------- */
/**
 * Remember an audio player's position and speed, and restore them next time.
 * @param {HTMLAudioElement} audio The player
 * @param {string} key Storage key for this course and lecture
 */
function attachAudioResume(audio, key) {
  if (!audio) return;
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { saved = null; }
  audio.addEventListener('loadedmetadata', () => {
    if (saved && saved.t > 5 && saved.t < audio.duration - 5) {
      audio.currentTime = saved.t;
      showToast(`從上次的 ${Math.floor(saved.t / 60)} 分 ${Math.floor(saved.t % 60)} 秒繼續`, 'info', 3000);
    }
    if (saved && saved.r) audio.playbackRate = saved.r;
  }, { once: true });
  let last = 0;
  /** Save the current position and speed for this course and lecture. */
  const save = () => {
    try { localStorage.setItem(key, JSON.stringify({ t: audio.currentTime, r: audio.playbackRate })); } catch (e) { /* storage blocked */ }
  };
  audio.addEventListener('timeupdate', () => { if (Date.now() - last > 5000) { last = Date.now(); save(); } });
  audio.addEventListener('ratechange', save);
  audio.addEventListener('pause', save);
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

/* ---------- Start-up ---------- */
document.addEventListener('DOMContentLoaded', () => {
  let saved = null;
  try { saved = localStorage.getItem('studioTheme'); } catch (e) { saved = null; }
  applyTheme(saved);
});

/* Every remaining alert() becomes a non-blocking toast; the type follows the message. */
window.alert = message => {
  const text = String(message);
  const type = /失敗|錯誤|error/i.test(text) ? 'error' : /✅|成功|已/.test(text) ? 'success' : 'info';
  showToast(text, type);
};
