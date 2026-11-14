/**
 * Gemini Notebook 學習工作室 — mock-exam timer, spaced-review flashcards, audio resume, and add-course wizard.
 * Loaded immediately after studio.js (relies on currentStudyCourse, activeStudyLectureNo, submitQuizAttempt,
 * currentFlashcards, currentFlashcardIdx, nextFlashcard, prefLoad, prefSave, previewFolders, showToast).
 */

let mockTimer = null;

/**
 * Start the mock-exam countdown (1.5 minutes per question); submits automatically at zero.
 * @param {number} questionCount Number of questions
 */
function startMockTimer(questionCount) {
  stopMockTimer();
  let left = Math.round(questionCount * 1.5 * 60);
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
    body: JSON.stringify({
      kind: 'flashcard', key: await cardKey(card.front), remembered,
      lecture_no: lectureNo, front: card.front, back: card.back,
    }),
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
 * Remember where the student stopped in an audio track and continue there next time.
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
      audio.currentTime = saved.t;
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
