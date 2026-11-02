/* Gemini Notebook 學習工作室 — mock API for the standalone demo (docs/demo/index.html).
   Replaces window.fetch before the app loads and answers every /api/... request in the browser from the
   fictional courses in demo-data.js. What you do is kept in this browser (localStorage "demo.state"),
   so a submitted quiz creates mistakes, rated cards move through the review boxes and finished steps
   show on the overview. Nothing is sent anywhere. */

const DEMO_STORE = 'demo.state';
const DAY = 86400000;
const STEP_DEFS = [['audio', '聽語音摘要'], ['guide', '讀讀書指南'], ['quiz_1', '測驗 1・基礎'], ['quiz_2', '測驗 2・理解'], ['quiz_3', '測驗 3・模擬考'], ['flashcards', '閃卡複習']];
const JOB_LABELS = {
  audio: '語音摘要', quiz_1: '測驗 1・基礎', quiz_2: '測驗 2・理解', quiz_3: '測驗 3・模擬考', study_guide: '讀書指南',
  reports_concept_explanation: '報告：概念解說', reports_briefing: '報告：簡報文件', mind_map: '心智圖', infographic: '資訊圖表',
  flashcards: '學習卡', data_table: '資料表', slide_deck: '簡報投影片', video: '影片摘要',
  course_audio: '全課語音摘要', course_mock_exam: '全課期末模擬考', course_mind_map: '全課跨章心智圖', course_reports_study_guide: '全課研讀指南',
};
const EXT = { audio: 'm4a', course_audio: 'm4a', mind_map: 'json', course_mind_map: 'json', infographic: 'png', flashcards: 'json', data_table: 'csv', slide_deck: 'pdf', video: 'mp4' };

/**
 * Two-digit number.
 * @param {number} n Number
 * @returns {string} e.g. "03"
 */
function demoPad(n) { return String(n).padStart(2, '0'); }

/**
 * A course from demo-data.js.
 * @param {string} code Course code
 * @returns {object|undefined} Course
 */
function demoCourse(code) { return DEMO_COURSES.find(c => c.code === code); }

/**
 * The full question objects of a lecture's quiz bank.
 * @param {object} lec Lecture from demo-data.js
 * @param {number} no Lecture number
 * @returns {Array<object>} Questions {question, choices, answer_index, explanation, source}
 */
function demoQuestions(lec, no) {
  return lec.quiz.map(([question, choices, answer, explanation]) => ({ question, choices: [...choices], answer_index: answer, explanation, source: `L${demoPad(no)}` }));
}

/** Build the starting state (from DEMO_SEED) the first time the demo opens. */
function demoInitialState() {
  const now = Date.now();
  const st = { attempts: [], mistakes: [], steps: [], cards: [], explanations: {}, tutor: {}, keyPoints: {}, today: new Date().toDateString(), todayCount: 0, prefs: {} };
  DEMO_SEED.attempts.forEach((a, i) => st.attempts.push({ id: `a${i}`, course_code: a.course, lecture_no: a.lecture, quiz_variant: a.variant, score: a.score, total_questions: a.total, created_at: new Date(now - a.daysAgo * DAY).toISOString() }));
  DEMO_SEED.mistakes.forEach((m, i) => {
    const lec = demoCourse(m.course).lectures[m.lecture - 1], q = demoQuestions(lec, m.lecture)[m.q];
    st.mistakes.push({ id: `m${i}`, course_code: m.course, lecture_no: m.lecture, question_text: q.question, choices: q.choices, correct_index: q.answer_index, selected_index: m.selected, explanation: q.explanation, confidence: m.confidence, is_resolved: false });
  });
  st.steps = DEMO_SEED.steps.map(([c, l, s]) => `${c}|${l}|${s}`);
  DEMO_SEED.due.forEach(([c, l, idx, stage]) => {
    const [front, back] = demoCourse(c).lectures[l - 1].cards[idx];
    st.cards.push({ course: c, lecture: l, front, back, stage, dueAt: now - 3600000 });
  });
  return st;
}

/** Read the demo state from this browser (or create it). */
function demoLoad() {
  let st = null;
  try { st = JSON.parse(localStorage.getItem(DEMO_STORE) || 'null'); } catch (e) { st = null; }
  if (!st) st = demoInitialState();
  if (st.today !== new Date().toDateString()) { st.today = new Date().toDateString(); st.todayCount = 0; }
  return st;
}
let demoState = demoLoad();

/** Keep the demo state in this browser. */
function demoSave() {
  try { localStorage.setItem(DEMO_STORE, JSON.stringify(demoState)); } catch (e) { /* private mode: keep in memory */ }
}

/** Count one study action today (for the check-in calendar and streak). */
function demoStudied() { demoState.todayCount += 1; demoSave(); }

/**
 * Every job (generated output) of a course, with statuses that make the batch page look busy.
 * @param {object} c Course
 * @returns {Array<object>} Jobs
 */
function demoJobs(c) {
  const jobs = [];
  /**
   * Add one job.
   * @param {number|null} no Lecture number (null = whole course)
   * @param {string} type Artifact type
   * @param {string} status Job status
   */
  const add = (no, type, status) => {
    const prefix = no === null ? 'ALL' : `L${demoPad(no)}`;
    const quiz = /quiz|mock_exam/.test(type);
    const file = quiz ? `${prefix}_${type}_quiz.json` : `${prefix}_${type}.${EXT[type] || 'md'}`;
    jobs.push({ id: `${c.code}-${prefix}-${type}`, course_code: c.code, lecture_no: no, artifact_type: type, label: JOB_LABELS[type] || type, status, version: type === 'infographic' && no === 1 ? 2 : 1,
      output_file: status === 'done' ? file : null, rel_path: status === 'done' ? file : null, style_options: type === 'quiz_3' && no === 2 ? '{"quiz_questions": 40}' : null,
      error_message: null, cooldown_until: status === 'quota_wait' ? new Date(Date.now() + 47 * 60000).toISOString() : null });
  };
  const n = c.lectures.length;
  c.lectures.forEach((lec, i) => {
    const no = i + 1, last = no === n && c.code === 'BIO101';
    ['audio', 'quiz_1', 'quiz_2', 'quiz_3', 'study_guide', 'reports_concept_explanation', 'reports_briefing', 'mind_map', 'infographic', 'flashcards', 'data_table'].forEach((t, k) => {
      add(no, t, last ? (k === 0 ? 'running' : k < 3 ? 'pending' : 'quota_wait') : 'done');
    });
    if (no <= 2) add(no, 'slide_deck', 'done');
    if (no === 1 && c.code === 'BIO101') add(no, 'video', 'done');
  });
  ['course_audio', 'course_mock_exam', 'course_mind_map', 'course_reports_study_guide'].forEach(t => add(null, t, 'done'));
  return jobs;
}

/**
 * The course as GET /api/courses/{code} returns it.
 * @param {object} c Course
 * @returns {object} Course with lectures and jobs
 */
function demoCourseJson(c) {
  return {
    code: c.code, name: c.name, paused: false, notebook_id: `demo-${c.code}`,
    exam_date: c.examInDays === null ? null : new Date(Date.now() + c.examInDays * DAY).toISOString().slice(0, 10),
    lectures: c.lectures.map((l, i) => ({ no: i + 1, topic: l.topic, filename: `${demoPad(i + 1)}_${l.title.replace(/ /g, '-')}.pdf`, upload_status: 'ready', source_id: `src-${c.code}-${i + 1}` })),
    jobs: demoJobs(c),
  };
}

/**
 * The study plan: steps per lecture (done from attempts, finished steps and reviews), next step, reviews due.
 * @param {object} c Course
 * @returns {object} Plan like GET /study/plan
 */
function demoPlan(c) {
  const course = demoCourseJson(c);
  let next = null;
  const lectures = c.lectures.map((lec, i) => {
    const no = i + 1;
    const doneJob = t => course.jobs.some(j => j.lecture_no === no && j.artifact_type === t && j.status === 'done');
    const steps = STEP_DEFS.map(([step, label]) => {
      const type = { guide: 'study_guide' }[step] || step;
      const available = doneJob(type);
      const done = step.startsWith('quiz')
        ? demoState.attempts.some(a => a.course_code === c.code && a.lecture_no === no && a.quiz_variant.endsWith(step))
        : demoState.steps.includes(`${c.code}|${no}|${step}`);
      if (available && !done && !next) next = { lecture_no: no, topic: lec.topic, step, label };
      return { step, label, available, done };
    });
    const avail = steps.filter(s => s.available);
    return { lecture_no: no, topic: lec.topic, steps, percent: avail.length ? Math.round(100 * avail.filter(s => s.done).length / avail.length) : 0 };
  });
  return {
    code: c.code, name: c.name, exam_date: course.exam_date, days_left: c.examInDays,
    due: { flashcards: demoState.cards.filter(k => k.course === c.code && k.dueAt <= Date.now()).length, mistakes: demoState.mistakes.filter(m => m.course_code === c.code && !m.is_resolved).length },
    next, lectures,
  };
}

/**
 * Memory strength per lecture, streak and the 28-day activity calendar.
 * @param {object} c Course
 * @returns {object} Like GET /study/memory
 */
function demoMemory(c) {
  const lectures = c.lectures.map((lec, i) => {
    const tries = demoState.attempts.filter(a => a.course_code === c.code && a.lecture_no === i + 1);
    if (!tries.length) return { no: i + 1, topic: lec.topic, percent: null };
    const last = tries[tries.length - 1], days = Math.max(0, Math.round((Date.now() - new Date(last.created_at)) / DAY));
    const percent = Math.max(20, Math.round(tries.reduce((s, a) => s + a.score / a.total_questions, 0) / tries.length * 100) - days * 6);
    return { no: i + 1, topic: lec.topic, percent, level: percent >= 75 ? 'strong' : percent >= 50 ? 'fading' : 'weak', days_since: days };
  });
  const heatmap = DEMO_SEED.activity.map((count, i) => {
    const d = new Date(Date.now() - (27 - i) * DAY);
    const iso = `${d.getFullYear()}-${demoPad(d.getMonth() + 1)}-${demoPad(d.getDate())}`;
    return { date: iso, count: i === 27 ? count + demoState.todayCount : count };
  });
  let streak = 0;
  for (let i = heatmap.length - 1; i >= 0; i--) {
    if (heatmap[i].count > 0) streak += 1; else if (i === heatmap.length - 1) continue; else break;
  }
  return { lectures, streak, studied_today: heatmap[27].count > 0, heatmap };
}

/**
 * Generation option defaults and allowed values, built from the page's own option labels.
 * @returns {{defaults: object, choices: object}} Defaults and choices
 */
function demoOptions() {
  const defaults = { language: 'zh-TW', mock_exam_questions: 50, exam_date: '' }, choices = { language: ['zh-TW', 'en', 'bilingual'], mock_exam_questions: { min: 10, max: 100 }, exam_date: 'date' };
  Object.entries(OPTION_LABELS).forEach(([key, [, names]]) => {
    if (names && typeof names === 'object') { choices[key] = Object.keys(names); defaults[key] = Object.keys(names)[key === 'infographic_orientation' ? 1 : 0]; }
    else if (names === 'number') { choices[key] = { min: 10, max: 60 }; defaults[key] = 30; }
    else if (names === null) defaults[key] = true;
    else defaults[key] = '';
  });
  return { defaults, choices };
}

/**
 * A JSON response.
 * @param {*} data Body
 * @param {number} status HTTP status
 * @returns {Response} Response
 */
function demoJson(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

/**
 * Tell the visitor that a change is not really carried out in the demo.
 * @param {string} what What would have happened
 */
function demoNote(what) {
  setTimeout(() => { if (typeof showToast === 'function') showToast(`示範版：${what}不會真的執行。`, 'info', 3500); }, 450);
}

/**
 * Answer one study request (/api/courses/{code}/study/...).
 * @param {object} c Course
 * @param {string} rest Path after /study/
 * @param {string} method HTTP method
 * @param {object} body Request body
 * @param {URLSearchParams} q Query
 * @returns {Response} Response
 */
function demoStudy(c, rest, method, body, q) {
  const code = c.code;
  if (rest === 'history') return demoJson(demoState.attempts.filter(a => a.course_code === code && (!q.has('lecture_no') || String(a.lecture_no) === q.get('lecture_no'))));
  if (rest === 'mistakes') return demoJson(demoState.mistakes.filter(m => m.course_code === code && !m.is_resolved && (!q.get('lecture_no') || String(m.lecture_no) === q.get('lecture_no'))));
  if (/^mistakes\/[^/]+\/resolve$/.test(rest)) { const m = demoState.mistakes.find(x => x.id === rest.split('/')[1]); if (m) m.is_resolved = true; demoStudied(); return demoJson({ resolved: true }); }
  if (rest === 'quiz-attempts' && method === 'POST') {
    demoState.attempts.push({ id: `a${Date.now()}`, course_code: code, lecture_no: body.lecture_no, quiz_variant: body.quiz_variant, score: body.score, total_questions: body.total_questions, created_at: new Date().toISOString() });
    (body.mistakes || []).forEach(m => {
      if (demoState.mistakes.some(x => !x.is_resolved && x.question_text === m.question_text)) return;
      demoState.mistakes.push({ id: `m${Date.now()}${Math.random().toString(36).slice(2, 6)}`, course_code: code, lecture_no: body.lecture_no, ...m, is_resolved: false });
    });
    demoStudied();
    return demoJson({ saved: true });
  }
  if (rest === 'flashcards') {
    const lec = c.lectures[(parseInt(q.get('lecture_no'), 10) || 1) - 1];
    return demoJson({ cards: (lec ? lec.cards : []).map(([front, back]) => ({ front, back, source: lec.title })) });
  }
  if (rest === 'plan') return demoJson(demoPlan(c));
  if (rest === 'progress' && method === 'POST') {
    const key = `${code}|${body.lecture_no}|${body.step}`;
    demoState.steps = demoState.steps.filter(s => s !== key);
    if (body.done) demoState.steps.push(key);
    demoStudied();
    return demoJson({ ok: true });
  }
  if (rest === 'reviews/due') return demoJson(demoState.cards.filter(k => k.course === code && k.dueAt <= Date.now()).map(k => ({ kind: 'flashcard', key: k.front, lecture_no: k.lecture, front: k.front, back: k.back, stage: k.stage })));
  if (rest === 'reviews' && method === 'POST') {
    let card = demoState.cards.find(k => k.course === code && k.front === body.front);
    if (!card) { card = { course: code, lecture: body.lecture_no, front: body.front, back: body.back, stage: 0, dueAt: 0 }; demoState.cards.push(card); }
    card.stage = body.remembered ? Math.min(5, card.stage + 1) : 1;
    card.dueAt = Date.now() + (body.remembered ? [0, 1, 3, 7, 14, 30][card.stage] * DAY : 600000);
    demoStudied();
    return demoJson({ stage: card.stage, due_at: new Date(card.dueAt).toISOString() });
  }
  if (rest === 'explanations') return demoJson(Object.values(demoState.explanations).filter(e => e.course === code));
  if (rest === 'explain' && method === 'POST') {
    const saved = demoState.explanations[body.question];
    if (saved && !body.force) return demoJson({ answer: saved.answer_md, html: saved.html, saved_at: saved.created_at, from_cache: true });
    const right = body.choices[body.answer_index];
    const html = `<p><strong>答案是「${right}」。</strong></p><p>先回到講義找出這個概念的定義，再比較其他選項錯在哪裡：它們各自描述的是相近但不同的機制。</p><ul><li>記住關鍵字，連到講義上的重點畫線。</li><li>用自己的話說一次，比重讀更記得住。</li></ul><p class="small">（示範版的解釋是預先寫好的範例。）</p>`;
    demoState.explanations[body.question] = { course: code, question: body.question, answer_md: html, html, created_at: new Date().toISOString() };
    demoSave();
    return demoJson({ answer: html, html, saved_at: new Date().toISOString(), from_cache: false });
  }
  if (rest === 'memory') return demoJson(demoMemory(c));
  if (rest.startsWith('tutor')) {
    const key = `${code}|${q.get('lecture_no') ?? (body && body.lecture_no) ?? 'all'}`;
    const log = demoState.tutor[key] || (demoState.tutor[key] = []);
    if (method === 'DELETE') { demoState.tutor[key] = []; demoSave(); return demoJson({ cleared: true }); }
    if (method === 'POST') {
      log.push({ role: 'student', text: body.message });
      const reply = `<p>好問題。我們一步一步來：</p><p>你覺得「${String(body.message).slice(0, 24)}」和這一講的哪一個重點最有關？先說說你的想法，我再引導你往下想。</p>`;
      log.push({ role: 'tutor', text: reply, html: reply });
      demoStudied();
      return demoJson({ text: reply, html: reply });
    }
    return demoJson(log);
  }
  return demoJson({ detail: 'not in demo' }, 404);
}

/**
 * Answer one course request (/api/courses/{code}/...).
 * @param {string} code Course code
 * @param {string} rest Path after the code ('' for the course itself)
 * @param {string} method HTTP method
 * @param {object} body Request body
 * @param {URLSearchParams} q Query
 * @returns {Response} Response
 */
function demoCourseRoute(code, rest, method, body, q) {
  const c = demoCourse(code);
  if (!c) return demoJson({ detail: '找不到課程' }, 404);
  if (rest === '' && method === 'GET') return demoJson(demoCourseJson(c));
  if (rest === '' && method === 'DELETE') { demoNote('刪除課程'); return demoJson({ detail: '示範版不會刪除課程' }, 400); }
  if (rest.startsWith('study/')) return demoStudy(c, rest.slice(6), method, body, q);
  let m = rest.match(/^lectures\/(\d+)\/key-points$/);
  if (m) {
    const no = +m[1], lec = c.lectures[no - 1], key = `${code}|${no}`;
    if (method === 'POST') { demoState.keyPoints[key] = (lec && (lec.points.length ? lec.points : lec.laterPoints)) || []; demoSave(); }
    return demoJson({ points: demoState.keyPoints[key] || (lec ? lec.points : []), created_at: new Date().toISOString(), from_cache: method === 'GET' });
  }
  m = rest.match(/^lectures\/(\d+)\/quiz\/(.+)$/);
  if (m) {
    const variant = decodeURIComponent(m[2]);
    const lm = variant.match(/^L(\d+)_/);
    const questions = lm ? demoQuestions(c.lectures[+lm[1] - 1], +lm[1]) : c.lectures.flatMap((l, i) => demoQuestions(l, i + 1).slice(0, 2));
    return demoJson({ quiz: { title: variant, questions } });
  }
  if (rest === 'options') {
    const { defaults, choices } = demoOptions();
    if (method === 'PUT') demoNote('儲存課程設定');
    return demoJson({ options: { ...defaults, exam_date: demoCourseJson(c).exam_date || '' }, choices, defaults });
  }
  if (rest === 'artifact-types') {
    const pick = name => [...document.querySelectorAll(`input[name="${name}"]`)].map(i => ({ value: i.value, label: i.parentElement.textContent.trim() }));
    if (method === 'PUT') { demoNote('變更產出內容'); return demoJson({ queued: 0, revived: 0, skipped: 0 }); }
    const used = demoJobs(c).map(j => j.artifact_type);
    const chapter = pick('chap_art'), course = pick('course_art');
    return demoJson({ chapter: chapter.map(x => x.value).filter(v => used.includes(v)), course: course.map(x => x.value).filter(v => used.includes(v)), choices: { chapter, course } });
  }
  if (method === 'POST') { demoNote('這個動作'); return demoJson({ ok: true, notebook_id: 'demo', upload_status: 'ready', updated_jobs_count: 0, remote_artifacts_found: 0, synced_count: 0 }); }
  return demoJson({ detail: 'not in demo' }, 404);
}

/**
 * Answer an /api/... request from the demo data.
 * @param {URL} url Request URL
 * @param {string} method HTTP method
 * @param {object} body Parsed JSON body
 * @returns {Response} Response
 */
function demoRoute(url, method, body) {
  const path = url.pathname, q = url.searchParams;
  if (path === '/api/status') {
    const counts = { done: 0, running: 0, pending: 0, quota_wait: 0 };
    DEMO_COURSES.forEach(c => demoJobs(c).forEach(j => { counts[j.status] = (counts[j.status] || 0) + 1; }));
    return demoJson({ auth: { authenticated: true }, queue_running: true, queue_counts: counts, app_env: 'demo' });
  }
  if (path === '/api/notebooklm/quota') {
    return demoJson({ windows: [{ kind: 'five_hour', remaining_percent: 72, resets_at: new Date(Date.now() + 2.5 * 3600000).toISOString() }, { kind: 'weekly', remaining_percent: 64, resets_at: new Date(Date.now() + 3 * DAY).toISOString() }], source_limit: 50 });
  }
  if (path === '/api/courses' && method === 'GET') {
    return demoJson(DEMO_COURSES.map(c => {
      const jobs = demoJobs(c), counts = {};
      jobs.forEach(j => { counts[j.status] = (counts[j.status] || 0) + 1; });
      return { code: c.code, name: c.name, lecture_count: c.lectures.length, total_jobs: jobs.length, counts, notebook_id: `demo-${c.code}`, paused: false };
    }));
  }
  if (path === '/api/courses/preview') return demoJson([{ is_valid: true, course_code: 'DEMO200', course_name: '示範課程', lecture_count: 8, estimated_jobs: 96, quota_estimate_available: false }]);
  if (path === '/api/courses' && method === 'POST') return demoJson({ detail: '示範版不會真的加入課程；在本機版選講義資料夾就能加入。' }, 400);
  const cm = path.match(/^\/api\/courses\/([^/]+)\/?(.*)$/);
  if (cm) return demoCourseRoute(decodeURIComponent(cm[1]), cm[2], method, body, q);
  if (path === '/api/generation-options') return demoJson(demoOptions());
  if (path === '/api/usage-guide') {
    return demoJson({ note: '這是示範版：課程、題目與進度都是虛構的，所有操作只存在這個瀏覽器。', sections: [
      { heading: '開始', steps: ['在「批次排程」按「加入課程」，點選放講義 PDF 的資料夾。', '勾選要生成的產出物；額度用完會在重置後自動繼續。'] },
      { heading: '每一講的讀書順序', steps: ['聽語音摘要，掌握全貌。', '讀講義與重點畫線。', '做測驗，答錯的題目會收進弱點複習。', '翻學習卡，依間隔複習。'] },
    ] });
  }
  if (path === '/api/naming-guide') return demoJson({ rules: ['檔名：<課程代號>_<講次>_<主題>_<類型>[_vN]', '重新生成不覆蓋舊檔，標題加 (v2)'], artifacts: Object.entries(JOB_LABELS).slice(0, 8).map(([t, l]) => ({ artifact_type: t, label: l, meaning: l, notebooklm_title: `[Ch01] ${l}`, local_files: `BIO101_01_細胞的構造與功能_${t}` })) });
  if (path === '/api/folders') {
    return demoJson(q.get('path') ? { path: q.get('path'), parent: '/示範', pdf_count: 6, folders: [] }
      : { path: null, parent: null, pdf_count: 0, folders: [{ name: 'BIO101 細胞與分子生物學', path: '/示範/BIO101', pdf_count: 6 }, { name: 'CHEM110 普通化學', path: '/示範/CHEM110', pdf_count: 4 }] });
  }
  let m = path.match(/^\/api\/jobs\/([^/]+)\/(options|prompt)$/);
  if (m) {
    if (method !== 'GET') { demoNote('儲存'); return demoJson({ ok: true }); }
    if (m[2] === 'prompt') return demoJson({ custom_prompt: '請根據這份講義生成內容。對象：大學生。使用繁體中文；專有名詞附英文。' });
    const { defaults, choices } = demoOptions();
    return demoJson({ label: '這一份產出', fields: ['quiz_questions', 'quiz_difficulty', 'extra_instructions'], overrides: {}, effective: defaults, choices, defaults, unsupported: [] });
  }
  if (path.startsWith('/api/queue/')) { demoNote('控制佇列'); return demoJson({ ok: true, data: 0 }); }
  if (path === '/api/preferences' && method === 'GET') return demoJson({ values: demoState.prefs });
  if (path === '/api/preferences' && method === 'PUT') {
    Object.entries(body.values || {}).forEach(([k, v]) => { if (v === null) delete demoState.prefs[k]; else demoState.prefs[k] = v; });
    demoSave(); return demoJson({ values: demoState.prefs });
  }
  if (path === '/api/preferences/reset') {
    const keep = body.keep || [];
    Object.keys(demoState.prefs).forEach(k => { if (!keep.includes(k)) delete demoState.prefs[k]; });
    demoSave(); return demoJson({ values: demoState.prefs });
  }
  if (path === '/api/fonts' && method === 'GET') return demoJson({ fonts: [] });
  if (path.startsWith('/api/fonts')) return demoJson({ detail: '示範版無法下載字型；在本機版輸入 Google Fonts 名稱即可下載。' }, 400);
  return demoJson({ detail: 'not in demo' }, 404);
}

const demoNativeFetch = window.fetch.bind(window);
/**
 * fetch() for the demo: /api/... is answered locally, everything else goes to the network.
 * @param {RequestInfo} input URL or request
 * @param {RequestInit} init Options
 * @returns {Promise<Response>} Response
 */
window.fetch = async (input, init = {}) => {
  const url = new URL(typeof input === 'string' ? input : input.url, location.href);
  if (!url.pathname.startsWith('/api/') && !url.href.includes('/api/')) return demoNativeFetch(input, init);
  const apiPath = url.pathname.slice(url.pathname.indexOf('/api/'));
  const method = String(init.method || 'GET').toUpperCase();
  let body = {};
  try { body = init.body ? JSON.parse(init.body) : {}; } catch (e) { body = {}; }
  await new Promise(r => setTimeout(r, 60));  // a little latency, like a real server
  return demoRoute(new URL(apiPath + url.search, location.origin), method, body);
};
