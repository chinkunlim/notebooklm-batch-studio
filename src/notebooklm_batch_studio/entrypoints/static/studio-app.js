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
    select.innerHTML = '<option value="">還沒有課程</option>';
    renderCourseDirectory();
    renderCoursePicker();
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
 * Draw the 課程目錄 pane: every course on the left, the current course's lectures on the right.
 */
function renderCourseDirectory() {
  const list = document.getElementById('courseList');
  const count = document.getElementById('courseCount');
  count.textContent = currentCoursesList.length ? `${currentCoursesList.length} 門` : '';
  list.innerHTML = currentCoursesList.length ? currentCoursesList.map(c => {
    const stats = c.counts || {};
    const total = (c.total_jobs || 0) - (stats.skipped || 0);
    const pct = total > 0 ? Math.round(((stats.done || 0) / total) * 100) : 0;
    const on = currentStudyCourse && currentStudyCourse.code === c.code ? ' on' : '';
    return `<button class="course${on}" onclick="pickStudyCourse('${escHtml(c.code)}')"><span class="course-cover" style="background:${courseColour(c.code)}">${escHtml(String(c.code).slice(0, 3))}</span>
      <span style="min-width:0"><span class="course-name">${escHtml(c.name)}</span><span class="small muted">${c.lecture_count} 講　·　產出完成 ${pct}%</span><span class="bar"><i style="width:${pct}%"></i></span></span></button>`;
  }).join('') : '<div class="empty-state">還沒有課程。到「批次排程」按「加入課程」選講義資料夾。<br><button class="btn btn-soft" onclick="go(\'queue\')">前往批次排程</button></div>';

  const course = currentStudyCourse;
  document.getElementById('cdCode').textContent = course ? course.code : '';
  document.getElementById('cdName').textContent = course ? course.name : '選一門課';
  const lectures = course ? course.lectures || [] : [];
  const best = no => {
    const tries = studyHistory.filter(h => h.lecture_no === no && h.total_questions);
    return tries.length ? Math.max(...tries.map(a => Math.round((a.score / a.total_questions) * 100))) : null;
  };
  const doneOutputs = no => (course ? course.jobs || [] : []).filter(j => j.lecture_no === no && j.status === 'done').length;
  document.getElementById('cdMeta').textContent = course ? `${lectures.length} 講　·　測驗作答 ${studyHistory.length} 次　·　待複習錯題 ${studyMistakes.length} 題` : '';
  /**
   * One lecture row of the 課程目錄 list with its open button.
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

/**
 * Draw the course picker in the top bar (button with the current course, and the list it opens).
 */
function renderCoursePicker() {
  const course = currentStudyCourse;
  const cover = document.getElementById('cpCover');
  cover.textContent = course ? String(course.code).slice(0, 3) : '';
  cover.style.background = course ? courseColour(course.code) : 'var(--track)';
  document.getElementById('cpName').textContent = course ? course.name : (currentCoursesList.length ? '選一門課' : '還沒有課程');
  document.getElementById('cpMeta').textContent = course ? `${course.code}　·　${(course.lectures || []).length} 講` : '';
  const items = currentCoursesList.map(c => {
    const stats = c.counts || {};
    const total = (c.total_jobs || 0) - (stats.skipped || 0);
    const pct = total > 0 ? Math.round(((stats.done || 0) / total) * 100) : 0;
    const on = course && course.code === c.code;
    return `<button class="cp-item${on ? ' on' : ''}" role="option" aria-selected="${on}" data-code="${escHtml(c.code)}">
      <span class="cp-cover" style="background:${courseColour(c.code)}">${escHtml(String(c.code).slice(0, 3))}</span>
      <span class="cp-text"><b>${escHtml(c.name)}</b><span>${escHtml(c.code)}　·　${c.lecture_count} 講　·　產出 ${pct}%</span></span>
      ${on ? '<i class="icon-check"></i>' : ''}</button>`;
  }).join('');
  document.getElementById('coursePop').innerHTML = (items || '<p class="small muted" style="padding:12px">還沒有課程。</p>') +
    '<div class="cp-foot"><button class="btn btn-ghost btn-sm" data-manage>管理課程</button></div>';
}

/**
 * Open or close the course picker list.
 * @param {boolean} open True to open
 */
function setCoursePop(open) {
  document.getElementById('coursePick').classList.toggle('open', open);
  document.getElementById('coursePickBtn').setAttribute('aria-expanded', open);
  if (open) (document.querySelector('#coursePop .cp-item.on') || document.querySelector('#coursePop .cp-item'))?.focus();
}

document.getElementById('coursePickBtn').addEventListener('click', e => {
  e.stopPropagation();
  setCoursePop(!document.getElementById('coursePick').classList.contains('open'));
});
document.getElementById('coursePop').addEventListener('click', e => {
  if (e.target.closest('[data-manage]')) { setCoursePop(false); go('queue'); return; }
  const item = e.target.closest('.cp-item');
  if (!item) return;
  setCoursePop(false);
  if (!currentStudyCourse || item.dataset.code !== currentStudyCourse.code) pickStudyCourse(item.dataset.code);
});
document.getElementById('coursePop').addEventListener('keydown', e => {
  const items = [...document.querySelectorAll('#coursePop .cp-item')], i = items.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus(); }
  if (e.key === 'Escape') { setCoursePop(false); document.getElementById('coursePickBtn').focus(); }
});
document.addEventListener('click', e => { if (!e.target.closest('#coursePick')) setCoursePop(false); });

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
 * Show the quiz chooser and load one quiz (the first available when none is given).
 * @param {string|null} variant Quiz file variant
 * @returns {Promise<void>}
 */
async function loadQuizForChapter(variant) {
  stopMockTimer();
  if (!currentStudyCourse) return;
  const kinds = availableQuizzes();
  if (!variant || !kinds.some(k => k.variant === variant)) variant = kinds.length ? kinds[0].variant : null;
  activeQuizVariant = variant;
  document.getElementById('quizKindButtons').innerHTML = kinds.map(k =>
    `<button class="chip${k.variant === variant ? ' on' : ''}" style="--hue:var(--h-quiz)" onclick="loadQuizForChapter('${k.variant}')">${k.label}${k.version > 1 ? ` v${k.version}` : ''}</button>`).join('');

  const container = document.getElementById('quizContainer');
  document.getElementById('quizScoreHeader').textContent = '';
  document.getElementById('quizActionBar').style.display = 'none';
  container.innerHTML = '<p class="loading-line">正在載入題目與解析…</p>';

  if (!variant) {
    container.innerHTML = `<div class="empty-state">這個範圍還沒有完成的測驗。<br>可到「批次排程」的「產出內容」勾選後生成。<br><button class="btn btn-soft" onclick="go('queue')">前往批次排程</button></div>`;
    return;
  }
  const code = currentStudyCourse.code;
  const lecNo = activeStudyLectureNo !== null ? activeStudyLectureNo : 0;
  try {
    const res = await fetch(`/api/courses/${code}/lectures/${lecNo}/quiz/${encodeURIComponent(variant)}?with_answers=true`);
    if (!res.ok) throw new Error('尚無此測驗資料');
    currentQuizData = await res.json();
    currentQuizAnswers = {};
    const questions = (currentQuizData.quiz && currentQuizData.quiz.questions) || (currentQuizData.json_data && currentQuizData.json_data.questions);
    if (!questions || questions.length === 0) {
      container.innerHTML = '<div class="empty-state">這份測驗沒有題目，可到「批次排程」重新生成。</div>';
      return;
    }
    renderQuizQuestions(currentQuizData.quiz || currentQuizData.json_data, variant);
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
 * Draw every question of a quiz (choices reshuffled on every attempt).
 * @param {{questions: Array}} quiz Quiz data
 * @param {string} variant Quiz variant (unused here; kept for add-ons that wrap this function)
 */
function renderQuizQuestions(quiz, variant) {
  const container = document.getElementById('quizContainer');
  container.innerHTML = '';
  currentQuizAnswers = {};
  // New choice order on every attempt (first try, full retake and wrong-only retake).
  quiz.questions = quiz.questions.map(q => shuffleQuestion(q));
  quiz.questions.forEach((q, qIdx) => {
    const card = document.createElement('div');
    card.className = 'q-card';
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
}

/**
 * Update the "answered n / total" text on the submit bar.
 */
function updateQuizProgress() {
  const questions = (currentQuizData.quiz && currentQuizData.quiz.questions) || (currentQuizData.json_data && currentQuizData.json_data.questions);
  document.getElementById('quizProgressText').textContent = `已作答 ${Object.keys(currentQuizAnswers).length} / ${questions.length} 題`;
}

/**
 * Grade the quiz, show answers and explanations, and save the attempt (wrong answers go to 弱點複習).
 * @returns {Promise<void>}
 */
async function submitQuizAttempt() {
  const questions = (currentQuizData.quiz && currentQuizData.quiz.questions) || (currentQuizData.json_data && currentQuizData.json_data.questions);
  const total = questions.length;
  let score = 0;
  const mistakes = [];
  const wrongIndexes = [];
  questions.forEach((q, qIdx) => {
    const selected = currentQuizAnswers[qIdx] !== undefined ? currentQuizAnswers[qIdx] : -1;
    const correct = q.answer_index;
    const expEl = document.getElementById(`explanation-${qIdx}`);
    if (expEl) expEl.style.display = 'block';
    (q.choices || []).forEach((c, cIdx) => {
      const el = document.getElementById(`choice-${qIdx}-${cIdx}`);
      if (!el) return;
      if (cIdx === correct) el.classList.add('correct');
      else if (cIdx === selected) el.classList.add('wrong');
    });
    if (selected === correct) {
      score++;
    } else {
      wrongIndexes.push(qIdx);
      mistakes.push({
        question_text: q.question,
        choices: q.choices.map(c => (c.text !== undefined ? c.text : c)),
        correct_index: correct,
        selected_index: selected,
        explanation: q.explanation || '',
        confidence: (window.quizConfidence || {})[qIdx] || null,
      });
    }
  });
  const pct = Math.round((score / total) * 100);
  document.getElementById('quizScoreHeader').textContent = `得分 ${score} / ${total}（${pct}%）`;
  renderQuizResult(score, total, wrongIndexes);

  const code = currentStudyCourse.code;
  try {
    await fetch(`/api/courses/${code}/study/quiz-attempts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        lecture_no: activeQuizVariant === 'mixed_review' ? null : activeStudyLectureNo,
        quiz_variant: activeQuizVariant,
        score,
        total_questions: total,
        mistakes,
        confidence: typeof confidenceSummary === 'function' ? confidenceSummary(wrongIndexes, total) : null,
      }),
    });
    loadStudyCourseData(code, true);
    loadWeaknessNotebook();
    if (mistakes.length) showToast(`${mistakes.length} 題錯題已收進「弱點複習」`, 'info');
  } catch (e) {
    console.error('Failed to save attempt:', e);
  }
}

/* ================= 弱點複習: mistakes ================= */

/**
 * Load every open mistake of the course and draw the list (grouped by lecture) and one question's detail.
 * @param {string} [selectId] Mistake to show; the first one when missing
 * @returns {Promise<void>}
 */
async function loadWeaknessNotebook(selectId) {
  const list = document.getElementById('mistakeList');
  const detail = document.getElementById('mistakeDetail');
  if (!currentStudyCourse) return;
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/mistakes?only_unresolved=true`);
    window.currentMistakes = res.ok ? await res.json() : [];
    await loadSavedExplanations();
  } catch (e) {
    list.innerHTML = '<li class="empty-state">讀不到錯題紀錄。</li>';
    return;
  }
  const mistakes = window.currentMistakes;
  if (!mistakes.length) {
    list.innerHTML = '<li class="empty-state">目前沒有待複習的錯題。<br><span class="small">測驗答錯的題目會自動收進這裡。</span></li>';
    detail.innerHTML = '<p class="muted">做完一回測驗後，答錯的題目會出現在左邊，點一題就能看詳解、問 Gemini Notebook 為什麼。</p>';
    return;
  }
  const groups = new Map();
  mistakes.forEach(m => {
    const key = m.lecture_no ?? 'course';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(m);
  });
  const keys = [...groups.keys()].sort((a, b) => (a === 'course') - (b === 'course') || a - b);
  list.innerHTML = keys.map(key => {
    const no = key === 'course' ? null : key;
    const label = no === null ? '整門課' : `${lectureName(no)}　${escHtml(lectureTopic(no))}`;
    return `<li class="group-label">${label}</li>` + groups.get(key).map(m => `<li><button class="mq" data-mid="${escHtml(m.id)}" onclick="showMistake('${escHtml(m.id)}')">
      <span class="mistake-q">${escHtml(m.question_text)}</span>${m.confidence === 'sure' ? '<span class="tag warn">很確定卻答錯</span>' : '<span class="tag">待複習</span>'}</button></li>`).join('');
  }).join('');
  const first = mistakes.find(m => m.id === selectId) || mistakes[0];
  showMistake(first.id);
}

/**
 * Show one mistake: the choices (yours and the right one), the explanation, and what to do next.
 * @param {string} id Mistake id
 */
function showMistake(id) {
  const m = (window.currentMistakes || []).find(x => x.id === id);
  if (!m) return;
  document.querySelectorAll('#mistakeList button[data-mid]').forEach(b => b.classList.toggle('on', b.dataset.mid === id));
  const lec = m.lecture_no ?? null;
  const opts = (m.choices || []).map((c, idx) => {
    const cls = idx === m.correct_index ? ' right' : idx === m.selected_index ? ' wrong' : '';
    const note = idx === m.correct_index ? '（正確答案）' : idx === m.selected_index ? '（你的答案）' : '';
    return `<div class="opt${cls}">${String.fromCharCode(65 + idx)}. ${escHtml(c)}${note}</div>`;
  }).join('');
  document.getElementById('mistakeDetail').innerHTML = `
    <div class="eyebrow">${lectureName(lec)}${lec !== null ? `　·　${escHtml(lectureTopic(lec))}` : ''}</div>
    <p class="q-title" style="margin:8px 0 16px">${escHtml(m.question_text)}</p>
    <div class="opts" style="--hue:var(--h-quiz)">${opts}</div>
    <div class="explain"><b>解析</b><br>${escHtml(m.explanation || '暫無解析')}</div>
    ${explanationSlot(m.question_text, `explainMistake('${m.id}', this)`, `explainMistake('${m.id}', this, true)`)}
    <div class="row section-gap" style="flex-wrap:wrap">
      <button class="btn btn-primary" onclick="resolveMistake('${m.id}')">我已經會了</button>
      <button class="btn btn-soft" onclick="practiseLecture(${lec === null ? 'null' : lec})">練習這一講</button>
      <button class="btn btn-ghost" onclick="askTutorAbout(${lec === null ? 'null' : lec})">問 AI 家教</button>
    </div>`;
}

/**
 * Open the quizzes of a lecture in the study page.
 * @param {number|null} no Lecture number
 */
function practiseLecture(no) {
  selectStudyLecture(no);
  switchStudyTab('quiz');
}

/**
 * Open the tutor for a lecture in the study page.
 * @param {number|null} no Lecture number
 */
function askTutorAbout(no) {
  selectStudyLecture(no);
  switchStudyTab('tutor');
}

/**
 * Mark a mistake as mastered (it leaves the list) and show the next one.
 * @param {string} id Mistake id
 * @returns {Promise<void>}
 */
async function resolveMistake(id) {
  const code = currentStudyCourse.code;
  try {
    await fetch(`/api/courses/${code}/study/mistakes/${id}/resolve`, { method: 'POST' });
    const list = window.currentMistakes || [];
    const i = list.findIndex(m => m.id === id);
    const next = list[i + 1] || list[i - 1];
    showToast('已移出錯題集', 'success', 2200);
    await loadWeaknessNotebook(next ? next.id : undefined);
    loadStudyCourseData(code, true);
  } catch (e) {
    showToast('標記失敗：' + e.message, 'error');
  }
}

/**
 * Download every open mistake of the course as an Anki CSV.
 */
function downloadWeaknessAnki() {
  if (!currentStudyCourse) return;
  window.location.href = `/api/courses/${currentStudyCourse.code}/study/mistakes/anki.csv`;
}

/* ================= Flashcards (study page) ================= */

/**
 * Load the current lecture's flashcards.
 * @returns {Promise<void>}
 */
async function loadFlashcardsViewer() {
  const container = document.getElementById('flashcardsViewerContainer');
  if (!currentStudyCourse) return;
  if (activeStudyLectureNo === null) {
    container.innerHTML = '<div class="empty-state">學習卡是一講一份：請先在「課程目錄」選一講。<br>到期要複習的卡片在「弱點複習」的「今日學習卡」。</div>';
    return;
  }
  container.innerHTML = '<p class="loading-line">正在載入學習卡…</p>';
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/study/flashcards?lecture_no=${activeStudyLectureNo}`);
    const data = await res.json();
    currentFlashcards = data.cards || [];
    currentFlashcardIdx = 0;
    if (!currentFlashcards.length) {
      container.innerHTML = '<div class="empty-state">這一講的學習卡還沒生成。<br>可到「批次排程」勾選學習卡後生成。</div>';
      return;
    }
    renderCurrentFlashcard();
  } catch (e) {
    container.innerHTML = '<div class="empty-state">載入學習卡失敗。</div>';
  }
}

/**
 * Draw the flashcard on screen with its navigation and rating buttons.
 */
function renderCurrentFlashcard() {
  const container = document.getElementById('flashcardsViewerContainer');
  const card = currentFlashcards[currentFlashcardIdx];
  const total = currentFlashcards.length;
  container.innerHTML = `
    <div class="flash-wrap">
      <div class="flashcard" id="studyFlash" onclick="toggleFlipCard()" role="button" tabindex="0" aria-label="翻面">
        <div class="flashcard-inner" id="flashcardInner">
          <div class="face">${escHtml(card.front)}</div>
          <div class="face back"><span>${escHtml(card.back)}${card.source ? `<span class="face-source">出處：${escHtml(card.source)}</span>` : ''}</span></div>
        </div>
      </div>
      <div class="row" style="justify-content:space-between;flex-wrap:wrap">
        <span class="row" style="gap:4px">
          <button class="icon-btn" onclick="prevFlashcard()" aria-label="上一張" ${currentFlashcardIdx === 0 ? 'disabled' : ''}><i class="icon-chevron-left"></i></button>
          <span class="flash-count">${currentFlashcardIdx + 1} / ${total}</span>
          <button class="icon-btn" onclick="nextFlashcard()" aria-label="下一張" ${currentFlashcardIdx === total - 1 ? 'disabled' : ''}><i class="icon-chevron-right"></i></button>
          <button class="btn btn-ghost btn-sm" onclick="shuffleFlashcards()">隨機抽卡</button>
        </span>
        <span class="row" style="gap:8px">
          <button class="btn btn-ghost" onclick="rateCurrentFlashcard(false)">不記得</button>
          <button class="btn btn-primary" onclick="rateCurrentFlashcard(true)">記得</button>
        </span>
      </div>
    </div>`;
}

/** Flip the flashcard on screen. */
function toggleFlipCard() {
  document.getElementById('studyFlash')?.classList.toggle('flipped');
}

/** Show the previous flashcard. */
function prevFlashcard() {
  if (currentFlashcardIdx > 0) { currentFlashcardIdx--; renderCurrentFlashcard(); }
}

/** Show the next flashcard. */
function nextFlashcard() {
  if (currentFlashcardIdx < currentFlashcards.length - 1) { currentFlashcardIdx++; renderCurrentFlashcard(); }
}

/** Shuffle the deck and start from the first card. */
function shuffleFlashcards() {
  currentFlashcards.sort(() => Math.random() - 0.5);
  currentFlashcardIdx = 0;
  renderCurrentFlashcard();
}

/**
 * Download the current lecture's flashcards as an Anki CSV.
 */
function downloadFlashcardsAnki() {
  if (!currentStudyCourse || activeStudyLectureNo === null) { showToast('請先選一講', 'warning'); return; }
  const job = (currentStudyCourse.jobs || []).find(j => j.artifact_type === 'flashcards' && j.lecture_no === activeStudyLectureNo);
  if (job && job.output_file) {
    const target = job.rel_path || job.output_file.split('/').pop();
    window.location.href = `/api/artifacts/${currentStudyCourse.code}/download/${encodeURIComponent(target.replace('.json', '.csv'))}`;
  } else {
    showToast('這一講還沒有學習卡 CSV', 'warning');
  }
}

/* ================= Reports, mind maps, infographics, slides, tables, video ================= */

/** Viewers for every document-like output (newest finished version first). */
const REPORT_KINDS = {
  guide: { label: '讀書指南', types: ['study_guide', 'reports_study_guide'] },
  concept: { label: '概念解說', types: ['reports_concept_explanation'] },
  briefing: { label: '簡報文件', types: ['reports_briefing'] },
  blog: { label: '部落格文章', types: ['reports_blog_post'] },
  infographic: { label: '資訊圖表', types: ['infographic'] },
  table: { label: '資料表', types: ['data_table'] },
  mindmap: { label: '心智圖', types: ['mind_map'] },
  slides: { label: '簡報投影片', types: ['slide_deck'] },
  video: { label: '影片摘要', types: ['video'] },
};
/** The report kinds shown as choices for the tile that is open (set by studio-shell.js). */
let currentReportGroup = ['guide', 'concept', 'briefing', 'blog'];

/**
 * The newest finished job of the given types in the current scope.
 * @param {Array<string>} types Artifact types (lecture names; course_ is added for the whole course)
 * @returns {object|undefined} Job
 */
function pickLatestJob(types) {
  const isCourse = activeStudyLectureNo === null;
  const wanted = types.map(t => (isCourse ? `course_${t}` : t));
  return (currentStudyCourse.jobs || [])
    .filter(j => wanted.includes(j.artifact_type) && j.output_file && ['done', 'needs_review'].includes(j.status)
      && (isCourse ? j.lecture_no === null : j.lecture_no === activeStudyLectureNo))
    .sort((a, b) => (b.version || 1) - (a.version || 1))[0];
}

/**
 * Parse CSV text (quoted cells, doubled quotes, BOM) into rows.
 * @param {string} text CSV text
 * @returns {Array<Array<string>>} Rows of cells
 */
function parseCsv(text) {
  const rows = []; let row = []; let cell = ''; let quoted = false;
  text = text.replace(/^﻿/, '');
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (ch !== '\r') cell += ch;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

/**
 * Show one document-like output inside the workbench (iframe, image, table or video by file type).
 * @param {string} kind Key of REPORT_KINDS
 * @returns {Promise<void>}
 */
async function loadReportInViewer(kind) {
  if (!currentStudyCourse) return;
  const group = currentReportGroup.includes(kind) ? currentReportGroup : [kind];
  document.getElementById('reportKindButtons').innerHTML = group.length > 1 ? group.map(key =>
    `<button class="chip${key === kind ? ' on' : ''}" style="--hue:var(--h-report)" onclick="loadReportInViewer('${key}')">${REPORT_KINDS[key].label}</button>`).join('') : '';
  const container = document.getElementById('reportContentContainer');
  const spec = REPORT_KINDS[kind] || REPORT_KINDS.guide;
  const job = pickLatestJob(spec.types);
  if (!job) {
    container.innerHTML = `<div class="empty-state">${activeStudyLectureNo === null ? '整門課' : '這一講'}還沒有「${spec.label}」。<br>可到「批次排程」的「產出內容」勾選後生成。<br><button class="btn btn-soft" onclick="go('queue')">前往批次排程</button></div>`;
    return;
  }
  const code = currentStudyCourse.code;
  const path = job.rel_path || job.output_file.split('/').pop();
  const enc = encodeURI(path);
  const dl = `/api/artifacts/${code}/download/${enc}`;
  const readable = ['guide', 'concept'].includes(kind) && activeStudyLectureNo !== null;
  const header = `<div class="report-meta"><span class="tag">v${job.version || 1}</span>${job.status === 'needs_review' ? '<span class="tag warn">需審查</span>' : ''}
    <a href="${dl}" target="_blank" rel="noopener">開新分頁 / 下載</a><span class="spacer"></span>${readable ? `<button class="btn btn-soft btn-sm" onclick="markStep('guide')">我讀完了</button>` : ''}</div>`;
  const ext = path.split('.').pop().toLowerCase();
  if (['md', 'opml', 'json'].includes(ext)) {
    container.innerHTML = header + `<iframe class="report-frame" src="/api/artifacts/${code}/view/${enc}" title="${escHtml(spec.label)}"></iframe>`;
  } else if (ext === 'png') {
    const stem = path.replace(/\.png$/, '');
    const extras = [['_A4.pdf', 'A4 PDF'], ['_iPadAir4.png', 'iPad Air 4'], ['_MacBookPro14.png', 'MacBook Pro 14']];
    const links = [];
    for (const [suffix, name] of extras) {
      const url = `/api/artifacts/${code}/download/${encodeURI(stem + suffix)}`;
      try { if ((await fetch(url, { method: 'HEAD' })).ok) links.push(`<a class="btn btn-ghost btn-sm" href="${url}" target="_blank" rel="noopener">${name}</a>`); } catch (e) { /* optional copy */ }
    }
    container.innerHTML = header + (links.length ? `<div class="row small muted" style="flex-wrap:wrap;margin-bottom:var(--s3)">裝置版本 ${links.join('')}</div>` : '') +
      `<img class="report-img" src="${dl}" alt="${escHtml(spec.label)}">`;
  } else if (ext === 'csv') {
    const rows = parseCsv(await (await fetch(dl)).text()).filter(r => r.some(c => c.trim()));
    const [head, ...body] = rows;
    container.innerHTML = header + `<div class="reader"><table><thead><tr>${(head || []).map(c => `<th>${escHtml(c)}</th>`).join('')}</tr></thead>
      <tbody>${body.map(r => `<tr>${r.map(c => `<td>${escHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  } else if (['mp4', 'webm', 'mov'].includes(ext)) {
    container.innerHTML = header + `<video class="report-video" controls preload="metadata" src="${dl}"></video>`;
  } else if (ext === 'pdf' || ext === 'html') {
    container.innerHTML = header + `<iframe class="report-frame" src="${dl}" title="${escHtml(spec.label)}"></iframe>`;
  } else {
    container.innerHTML = header + `<div class="empty-state">這個格式（.${escHtml(ext)}）無法在網頁預覽，請用上方連結下載。</div>`;
  }
}
