/* Gemini Notebook 學習工作室 — study features: the study course and lecture, 課程目錄, quizzes, 弱點複習
   mistakes, study flashcards, and the report / mind map / infographic / slides / table / video viewer.
   Part of the page's former inline script (the batch page is in studio-batch.js and studio-settings.js);
   same API calls, rendered into the v05 pages of index.html.
   Globals used from the shell scripts: go, setChoice, onLectureChanged, onStudyDataChanged, prefLoad, prefSave. */

let activeJobId = null;
let activeCourseCode = null;
let currentCoursesList = [];
let currentStudyCourse = null;
let activeStudyLectureNo = null; // null represents course-wide
let activeStudyTab = 'today';
let activeQuizVariant = null;
let currentQuizData = null;
let currentQuizAnswers = {};
let currentFlashcards = [];
let currentFlashcardIdx = 0;
let studyHistory = [];
let studyMistakes = [];

/**
 * Escape text for safe insertion into HTML.
 * @param {*} s Any value
 * @returns {string} Escaped text ('' for null / undefined)
 */
function escHtml(s) {
  if (s === null || s === undefined) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

/**
 * Two-digit number, e.g. 3 -> "03".
 * @param {number} n Number
 * @returns {string} Padded text
 */
function pad2(n) {
  return String(n).padStart(2, '0');
}

/**
 * Human label for a lecture, e.g. "第 03 講" or "整門課".
 * @param {number|null} no Lecture number (null = whole course)
 * @returns {string} Label
 */
function lectureName(no) {
  return no === null || no === undefined ? '整門課' : `第 ${pad2(no)} 講`;
}

/**
 * Topic of a lecture in the current study course.
 * @param {number|null} no Lecture number
 * @returns {string} Topic or ''
 */
function lectureTopic(no) {
  if (!currentStudyCourse || no === null) return '';
  return ((currentStudyCourse.lectures || []).find(l => l.no === no) || {}).topic || '';
}

/**
 * Older entry point kept for callers that still switch "views".
 * @param {string} mode 'study' or 'admin'
 */
function switchMainView(mode) {
  go(mode === 'study' ? 'studio' : 'queue');
}

/* ================= Courses for studying ================= */

/**
 * Fill the course picker and open the remembered (or first) course.
 * @returns {Promise<void>}
 */
async function initStudyPortal() {
  const select = document.getElementById('studyCourseSelect');
  if (!currentCoursesList || currentCoursesList.length === 0) await fetchCourses();
  if (currentCoursesList.length === 0) {
    currentStudyCourse = null;
    activeStudyLectureNo = null;
    currentPlan = null;
    studyHistory = [];
    studyMistakes = [];
    currentQuizData = null;
    currentFlashcards = [];
    select.innerHTML = '<option value="">還沒有課程</option>';
    renderCourseDirectory();
    renderCoursePicker();
    await loadTodayPanel();
    onStudyDataChanged();
    return;
  }
  select.innerHTML = currentCoursesList.map(c => `<option value="${escHtml(c.code)}">${escHtml(c.code)}　${escHtml(c.name)}</option>`).join('');
  const remembered = prefLoad('course', '');
  const target = currentCoursesList.some(c => c.code === remembered) ? remembered : currentCoursesList[0].code;
  select.value = target;
  await loadStudyCourseData(target);
}

/**
 * Open the course chosen in the top-bar picker and remember it.
 * @returns {Promise<void>}
 */
async function onStudyCourseSelected() {
  const code = document.getElementById('studyCourseSelect').value;
  if (!code) return;
  prefSave('course', code);
  await loadStudyCourseData(code);
}

/**
 * Load one course with its study history and open mistakes, then refresh every study page.
 * @param {string} code Course code
 * @param {boolean} keepView True after a quiz is saved: only refresh numbers, stay on the same lecture
 * @returns {Promise<void>}
 */
async function loadStudyCourseData(code, keepView = false) {
  try {
    const res = await fetch(`/api/courses/${encodeURIComponent(code)}`);
    if (!res.ok) throw new Error('無法載入課程');
    currentStudyCourse = await res.json();
    const [histRes, mistRes] = await Promise.all([
      fetch(`/api/courses/${encodeURIComponent(code)}/study/history`),
      fetch(`/api/courses/${encodeURIComponent(code)}/study/mistakes?only_unresolved=true`),
    ]);
    studyHistory = histRes.ok ? await histRes.json() : [];
    studyMistakes = mistRes.ok ? await mistRes.json() : [];
    const select = document.getElementById('studyCourseSelect');
    if (select.value !== code) select.value = code;
    renderCourseDirectory();
    renderCoursePicker();
    if (!keepView) {
      const place = typeof savedPlace === 'function' ? savedPlace() : null;
      const lectures = currentStudyCourse.lectures || [];
      const remembered = place && (place.lecture === null || lectures.some(l => l.no === place.lecture)) ? place.lecture : undefined;
      selectStudyLecture(remembered !== undefined ? remembered : (lectures.length ? lectures[0].no : null));
      loadWeaknessNotebook();
      if (typeof loadReviewCards === 'function') loadReviewCards();
    }
    loadTodayPanel();
    onStudyDataChanged();
  } catch (e) {
    console.error('Failed to load study course:', e);
    showToast('讀不到這門課：' + e.message, 'error');
  }
}

/**
 * Colour for a course cover, stable per course code.
 * @param {string} code Course code
 * @returns {string} CSS colour
 */
function courseColour(code) {
  const hues = ['#3f6f57', '#8a5b3e', '#44699a', '#85609a', '#2c8580', '#ad4f68', '#5759ab', '#b07d2a'];
  let h = 0;
  for (const ch of String(code)) h = (h * 31 + ch.charCodeAt(0)) % 9973;
  return hues[h % hues.length];
}

/**
 * Build HTML for the left course list in 課程目錄 under the active filter.
 * @returns {string} HTML for course list container
 */
function buildCourseDirectoryListHtml() {
  const filter = typeof load === 'function' ? load('courseFilter', 'all') : 'all';
  const filtered = currentCoursesList.filter(c => filter === 'all' || c.study_state === filter);
  document.getElementById('courseCount').textContent = currentCoursesList.length
    ? (filtered.length === currentCoursesList.length ? `${currentCoursesList.length} 門` : `${filtered.length} / ${currentCoursesList.length} 門`)
    : '';
  if (!filtered.length) {
    return currentCoursesList.length ? '<div class="empty-state">目前這個篩選分類下沒有課程。</div>' : '<div class="empty-state">還沒有課程。到「批次排程」按「加入課程」選講義資料夾。<br><button class="btn btn-soft" onclick="go(\'queue\')">前往批次排程</button></div>';
  }
  return filtered.map(c => {
    const stats = c.counts || {}, total = (c.total_jobs || 0) - (stats.skipped || 0);
    const pct = total > 0 ? Math.round(((stats.done || 0) / total) * 100) : 0;
    const on = currentStudyCourse && currentStudyCourse.code === c.code ? ' on' : '';
    return `<button class="course${on}" onclick="pickStudyCourse('${escHtml(c.code)}')"><span class="course-cover" style="background:${courseColour(c.code)}">${escHtml(String(c.code).slice(0, 3))}</span>
      <span style="min-width:0"><span class="course-name">${escHtml(c.name)}</span><span class="small muted">${c.lecture_count} 講　·　產出完成 ${pct}%</span><span class="bar"><i style="width:${pct}%"></i></span></span></button>`;
  }).join('');
}

/**
 * Draw the 課程目錄 pane: every course on the left, the current course's lectures on the right.
 */
function renderCourseDirectory() {
  document.getElementById('courseList').innerHTML = buildCourseDirectoryListHtml();
  const course = currentStudyCourse, lectures = course ? course.lectures || [] : [];
  document.getElementById('cdCode').textContent = course ? course.code : '';
  document.getElementById('cdName').textContent = course ? course.name : '選一門課';
  document.getElementById('cdMeta').textContent = course ? `${lectures.length} 講　·　測驗作答 ${studyHistory.length} 次　·　待複習錯題 ${studyMistakes.length} 題` : '';
  const best = no => {
    const tries = studyHistory.filter(h => h.lecture_no === no && h.total_questions);
    return tries.length ? Math.max(...tries.map(a => Math.round((a.score / a.total_questions) * 100))) : null;
  };
  const doneOutputs = no => (course ? course.jobs || [] : []).filter(j => j.lecture_no === no && j.status === 'done').length;
  /**
   * One lecture row HTML with its open button.
   * @param {number|null} no Lecture number (null = whole course)
   * @param {string} title Lecture topic
   * @param {string} meta Second line (best score, outputs)
   * @returns {string} HTML
   */
  const row = (no, title, meta) => {
    const current = activeStudyLectureNo === no;
    return `<li><span class="lec-no">${no === null ? '全' : no}</span><span><b>${escHtml(title)}</b><br><span class="small muted">${meta}</span></span>
      <button class="btn ${current ? 'btn-soft' : 'btn-ghost'}" onclick="openLecture(${no === null ? 'null' : no})">${current ? '研讀中' : '進入研讀'}</button></li>`;
  };
  document.getElementById('lectureList').innerHTML = course ? lectures.map(l => {
    const b = best(l.no);
    return row(l.no, l.topic, `${b !== null ? `最佳 ${b}%` : '還沒做測驗'}　·　${doneOutputs(l.no)} 項產出物`);
  }).join('') + row(null, '全課跨章總複習', `模擬考、全課心智圖與語音　·　${doneOutputs(null)} 項產出物`) : '';
}

/* Course picker popover helpers live in studio-study-panels.js. */

/**
 * Switch the study course from the 課程目錄 list.
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function pickStudyCourse(code) {
  prefSave('course', code);
  document.getElementById('studyCourseSelect').value = code;
  await loadStudyCourseData(code);
}

/**
 * Open one lecture in the 研讀 pane.
 * @param {number|null} no Lecture number (null = whole course)
 */
function openLecture(no) {
  selectStudyLecture(no);
  setChoice('studioPane', 'study', false);
}

/**
 * Make a lecture the current one and refresh what depends on it.
 * @param {number|null} lectureNo Lecture number (null = whole course)
 */
function selectStudyLecture(lectureNo) {
  activeStudyLectureNo = lectureNo;
  renderCourseDirectory();
  onLectureChanged();
}

/* ================= Quiz ================= */

/** Quizzes a student can take: lecture quizzes per chapter, mock exams for the whole course. */
const QUIZ_KINDS = {
  lecture: [['quiz_1', '測驗 1・基礎'], ['quiz_2', '測驗 2・理解'], ['quiz_3', '測驗 3・模擬考'],
            ['quiz_academic', '學術精研'], ['quiz_concept', '概念刷題']],
  course: [['course_mock_exam', '全課程模擬考'], ['course_quiz_academic', '全課程學術精研'],
           ['course_quiz_concept', '全課程概念刷題']],
};

/**
 * The finished quizzes for the current scope, newest version of each.
 * @returns {Array<{type: string, label: string, variant: string, version: number}>} Quizzes
 */
function availableQuizzes() {
  const isCourse = activeStudyLectureNo === null;
  return QUIZ_KINDS[isCourse ? 'course' : 'lecture'].map(([type, label]) => {
    const job = (currentStudyCourse.jobs || [])
      .filter(j => j.artifact_type === type && j.status === 'done' && j.output_file
        && (isCourse ? j.lecture_no === null : j.lecture_no === activeStudyLectureNo))
      .sort((a, b) => (b.version || 1) - (a.version || 1))[0];
    // The quiz files are named "<variant>[_vN]_quiz.json"; that prefix selects the newest version.
    const variant = job ? job.output_file.split('/').pop().replace(/_quiz\.json$/, '') : null;
    return { type, label, variant, version: job ? job.version || 1 : null };
  }).filter(k => k.variant);
}

/**
 * Fetch and render a single quiz variant once selected, adding mock-exam timer banner when needed.
 * @param {HTMLElement} container Quiz container element
 * @param {string} variant Selected quiz variant name
 * @returns {Promise<void>} Resolves when quiz questions are rendered
 */
async function fetchAndRenderQuizVariant(container, variant) {
  const code = currentStudyCourse.code, lecNo = activeStudyLectureNo !== null ? activeStudyLectureNo : 0;
  try {
    const res = await fetch(`/api/courses/${code}/lectures/${lecNo}/quiz/${encodeURIComponent(variant)}?with_answers=true`);
    if (!res.ok) throw new Error('尚無此測驗資料');
    currentQuizData = await res.json();
    currentQuizAnswers = {};
    const payload = currentQuizData.quiz || currentQuizData.json_data;
    const questions = payload && payload.questions;
    if (!questions || questions.length === 0) {
      container.innerHTML = '<div class="empty-state">這份測驗沒有題目，可到「批次排程」重新生成。</div>';
      return;
    }
    renderQuizQuestions(payload, variant);
    if (variant.startsWith('course_')) {
      const n = questions.length;
      container.insertAdjacentHTML('afterbegin',
        `<div class="plan-card row" style="justify-content:space-between;flex-wrap:wrap;margin-bottom:var(--s3)">
           <span class="small">模擬考模式：限時 ${Math.round(n * 1.5)} 分鐘，交卷前看不到答案，交卷後顯示各章答對率。</span>
           <button class="btn btn-primary btn-sm" onclick="startMockTimer(${n}); this.closest('.plan-card').remove();">開始計時</button></div>`);
    }
  } catch (e) {
    container.innerHTML = '<div class="empty-state">這份測驗還沒生成，可到「批次排程」排入生成。</div>';
  }
}

/**
 * Show the quiz chooser and load one quiz (the first available when none is given).
 * @param {string|null} variant Quiz file variant
 * @returns {Promise<void>} Resolves when quiz UI is updated
 */
async function loadQuizForChapter(variant) {
  stopMockTimer();
  if (!currentStudyCourse) return;
  const kinds = availableQuizzes();
  if (!variant || !kinds.some(k => k.variant === variant)) variant = kinds.length ? kinds[0].variant : null;
  activeQuizVariant = variant;
  document.getElementById('quizKindButtons').innerHTML = kinds.map(k =>
    `<button type="button" class="reader-pill-btn${k.variant === variant ? ' on' : ''}" onclick="loadQuizForChapter('${k.variant}')">${k.label}${k.version > 1 ? ` v${k.version}` : ''}</button>`).join('');
  const container = document.getElementById('quizContainer');
  document.getElementById('quizScoreHeader').textContent = '';
  document.getElementById('quizActionBar').style.display = 'none';
  container.innerHTML = '<p class="loading-line">正在載入題目與解析…</p>';
  if (!variant) {
    container.innerHTML = `<div class="empty-state">這個範圍還沒有完成的測驗。<br>可到「批次排程」的「產出內容」勾選後生成。<br><button class="btn btn-soft" onclick="go('queue')">前往批次排程</button></div>`;
    return;
  }
  await fetchAndRenderQuizVariant(container, variant);
}

let currentQuizIndex = 0;
let quizSubmitted = false;
let quizAutoTimer = null;

/**
 * Show only one question card at index idx and update pager buttons.
 * @param {number} idx Target 0-based question index
 */
function showQuizQuestion(idx) {
  const cards = [...document.querySelectorAll('#quizContainer .q-card')];
  if (!cards.length) return;
  currentQuizIndex = Math.max(0, Math.min(cards.length - 1, idx));
  cards.forEach((c, i) => { c.hidden = i !== currentQuizIndex; });
  const meta = document.getElementById('quizPagerMeta');
  if (meta) meta.textContent = `第 ${currentQuizIndex + 1} / ${cards.length} 題`;
  const prev = document.getElementById('quizPrevBtn');
  const next = document.getElementById('quizNextBtn');
  if (prev) prev.disabled = currentQuizIndex === 0;
  if (next) next.disabled = currentQuizIndex >= cards.length - 1;
}

/**
 * Step to the previous (-1) or next (+1) question in single-question quiz mode.
 * @param {number} delta -1 or 1
 */
function stepQuizQuestion(delta) {
  showQuizQuestion(currentQuizIndex + delta);
}

/**
 * Draw every question of a quiz (choices reshuffled on every attempt).
 * @param {{questions: Array}} quiz Quiz data
 * @param {string} variant Quiz variant (unused here; kept for add-ons that wrap this function)
 */
function renderQuizQuestions(quiz, variant) {
  const container = document.getElementById('quizContainer');
  container.innerHTML = '';
  currentQuizAnswers = {};
  currentQuizIndex = 0;
  quizSubmitted = false;
  clearTimeout(quizAutoTimer);
  // New choice order on every attempt (first try, full retake and wrong-only retake).
  quiz.questions = quiz.questions.map(q => shuffleQuestion(q));
  quiz.questions.forEach((q, qIdx) => {
    const card = document.createElement('div');
    card.className = 'q-card';
    card.dataset.qidx = String(qIdx);
    const choices = (q.choices || []).map((c, cIdx) => {
      const choiceText = c.text !== undefined ? c.text : c;
      return `<div class="choice-btn" id="choice-${qIdx}-${cIdx}" onclick="selectChoice(${qIdx}, ${cIdx})"><b>${String.fromCharCode(65 + cIdx)}.</b>${escHtml(choiceText)}</div>`;
    }).join('');
    card.innerHTML = `
      <div class="q-title">${qIdx + 1}. ${escHtml(q.question)}</div>
      <div>${choices}</div>
      <div class="q-explain" id="explanation-${qIdx}" style="display:none">
        <div class="answer">正確答案：${String.fromCharCode(65 + q.answer_index)}</div>
        <div>${escHtml(q.explanation || '暫無解析')}</div>
      </div>`;
    container.appendChild(card);
  });
  container.insertAdjacentHTML('beforeend', `<div class="quiz-pager" id="quizPager">
    <button type="button" class="btn btn-soft btn-sm" id="quizPrevBtn" onclick="stepQuizQuestion(-1)">← 上一題</button>
    <span class="quiz-pager-meta" id="quizPagerMeta"></span>
    <button type="button" class="btn btn-soft btn-sm" id="quizNextBtn" onclick="stepQuizQuestion(1)">下一題 →</button>
  </div>`);
  showQuizQuestion(0);
  document.getElementById('quizActionBar').style.display = 'flex';
  updateQuizProgress();
}

/**
 * Record the answer picked for one question.
 * @param {number} qIdx Question index
 * @param {number} cIdx Choice index
 */
function selectChoice(qIdx, cIdx) {
  currentQuizAnswers[qIdx] = cIdx;
  const questions = (currentQuizData.quiz && currentQuizData.quiz.questions) || (currentQuizData.json_data && currentQuizData.json_data.questions);
  for (let i = 0; i < questions[qIdx].choices.length; i++) {
    document.getElementById(`choice-${qIdx}-${i}`)?.classList.remove('selected');
  }
  document.getElementById(`choice-${qIdx}-${cIdx}`)?.classList.add('selected');
  updateQuizProgress();
  if (!quizSubmitted && (typeof load === 'function' ? load('quizAdvance', 'manual') : 'manual') === 'auto' && qIdx < questions.length - 1) {
    clearTimeout(quizAutoTimer);
    quizAutoTimer = setTimeout(() => showQuizQuestion(qIdx + 1), 320);
  }
}

/**
 * Update the "answered n / total" text on the submit bar.
 */
function updateQuizProgress() {
  const questions = (currentQuizData.quiz && currentQuizData.quiz.questions) || (currentQuizData.json_data && currentQuizData.json_data.questions);
  document.getElementById('quizProgressText').textContent = `已作答 ${Object.keys(currentQuizAnswers).length} / ${questions.length} 題`;
}

/**
 * Reveal answer explanations, highlight right/wrong DOM choices, and tally score and mistakes.
 * @param {Array<object>} questions Current quiz questions
 * @returns {{score: number, mistakes: Array<object>, wrongIndexes: Array<number>}} Graded summary
 */
function gradeQuizQuestionsDom(questions) {
  let score = 0;
  const mistakes = [], wrongIndexes = [];
  questions.forEach((q, qIdx) => {
    const selected = currentQuizAnswers[qIdx] !== undefined ? currentQuizAnswers[qIdx] : -1;
    const correct = q.answer_index, expEl = document.getElementById(`explanation-${qIdx}`);
    if (expEl) expEl.style.display = 'block';
    (q.choices || []).forEach((c, cIdx) => {
      const el = document.getElementById(`choice-${qIdx}-${cIdx}`);
      if (el && cIdx === correct) el.classList.add('correct');
      else if (el && cIdx === selected) el.classList.add('wrong');
    });
    if (selected === correct) score++;
    else {
      wrongIndexes.push(qIdx);
      mistakes.push({
        question_text: q.question, choices: q.choices.map(c => (c.text !== undefined ? c.text : c)),
        correct_index: correct, selected_index: selected, explanation: q.explanation || '',
        confidence: (window.quizConfidence || {})[qIdx] || null,
      });
    }
  });
  return { score, mistakes, wrongIndexes };
}

/**
 * Grade the quiz, show answers and explanations, and save the attempt (wrong answers go to 弱點複習).
 * @returns {Promise<void>} Resolves once attempt is posted
 */
async function submitQuizAttempt() {
  quizSubmitted = true;
  clearTimeout(quizAutoTimer);
  document.querySelectorAll('#quizContainer .q-card').forEach(c => { c.hidden = false; });
  const pager = document.getElementById('quizPager');
  if (pager) pager.style.display = 'none';
  const questions = (currentQuizData.quiz && currentQuizData.quiz.questions) || (currentQuizData.json_data && currentQuizData.json_data.questions);
  const total = questions.length;
  const { score, mistakes, wrongIndexes } = gradeQuizQuestionsDom(questions);
  const pct = Math.round((score / total) * 100);
  document.getElementById('quizScoreHeader').textContent = `得分 ${score} / ${total}（${pct}%）`;
  renderQuizResult(score, total, wrongIndexes);
  const code = currentStudyCourse.code;
  try {
    await fetch(`/api/courses/${code}/study/quiz-attempts`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lecture_no: activeQuizVariant === 'mixed_review' ? null : activeStudyLectureNo,
        quiz_variant: activeQuizVariant, score, total_questions: total, mistakes,
        confidence: typeof confidenceSummary === 'function' ? confidenceSummary(wrongIndexes, total) : null,
      }),
    });
    loadStudyCourseData(code, true);
    loadWeaknessNotebook();
    if (mistakes.length) showToast(`${mistakes.length} 題錯題已收進「弱點複習」`, 'info');
  } catch (e) { console.error('Failed to save attempt:', e); }
}

/* Weakness notebook, flashcards viewer, and document/report viewer live in studio-study-panels.js. */
