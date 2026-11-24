/**
 * Gemini Notebook 學習工作室 — course picker popover, weakness notebook, flashcards viewer, and document/report viewer.
 * Loaded immediately after studio-app.js (relies on escHtml, pad2, lectureName, lectureTopic, courseColour,
 * currentCoursesList, currentStudyCourse, activeStudyLectureNo, currentFlashcards, currentFlashcardIdx,
 * pickStudyCourse, selectStudyLecture, loadStudyCourseData, loadSavedExplanations, explanationSlot,
 * switchStudyTab, go, showToast).
 */

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

/* ================= 弱點複習: mistakes ================= */

/**
 * Load every open mistake of the course and draw the list (grouped by lecture) and one question's detail.
 * @param {string} [selectId] Mistake to show; the first one when missing
 * @returns {Promise<void>} Resolves when weakness list is drawn
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
    return `<li class="group-label">${label}</li>` + groups.get(key).map(m => `<li><button class="mq" data-mid="${escHtml(m.id)}" onclick="showMistake(${jsAttr(m.id)})">
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
      <button class="btn btn-primary" onclick="resolveMistake(${jsAttr(m.id)})">我已經會了</button>
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
 * @returns {Promise<void>} Resolves after updating mistake state
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

/** Download every open mistake of the course as an Anki CSV. */
function downloadWeaknessAnki() {
  if (!currentStudyCourse) return;
  window.location.href = `/api/courses/${currentStudyCourse.code}/study/mistakes/anki.csv`;
}

/* ================= Flashcards (study page) ================= */

/**
 * Load the current lecture's flashcards.
 * @returns {Promise<void>} Resolves when flashcards are loaded
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

/** Draw the flashcard on screen with its navigation and rating buttons. */
function renderCurrentFlashcard() {
  const container = document.getElementById('flashcardsViewerContainer');
  const card = currentFlashcards[currentFlashcardIdx];
  const total = currentFlashcards.length;
  container.innerHTML = `
    <div class="flash-wrap">
      <div class="flashcard" id="studyFlash" onclick="toggleFlipCard()" role="button" tabindex="0" aria-label="翻面">
        <div class="flashcard-inner" id="flashcardInner">
          <div class="face">${escHtml(card.front)}</div>
          <div class="face back"><span>${escHtml(card.back)}${card.source ? `<button type="button" class="face-source" style="cursor:pointer;text-decoration:underline;background:none;border:0;color:inherit;font:inherit;display:block;margin-top:8px" data-src="${escHtml(card.source)}" onclick="event.stopPropagation();if(typeof highlightQaCitationInPdf==='function')highlightQaCitationInPdf(this.dataset.src)">出處：${escHtml(card.source)}</button>` : ''}</span></div>
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

/** Download the current lecture's flashcards as an Anki CSV. */
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
 * Render optional device-formatted infographic links when available on disk.
 * @param {string} code Course code
 * @param {string} path Relative artifact PNG path
 * @returns {Promise<string>} HTML links row or empty string
 */
async function renderPngDeviceExtras(code, path) {
  const stem = path.replace(/\.png$/, '');
  const extras = [['_A4.pdf', 'A4 PDF'], ['_iPadAir4.png', 'iPad Air 4'], ['_MacBookPro14.png', 'MacBook Pro 14']];
  const links = [];
  for (const [suffix, name] of extras) {
    const url = `/api/artifacts/${code}/download/${encodeURI(stem + suffix)}`;
    try { if ((await fetch(url, { method: 'HEAD' })).ok) links.push(`<a class="btn btn-ghost btn-sm" href="${url}" target="_blank" rel="noopener">${name}</a>`); } catch (e) { /* optional copy */ }
  }
  return links.length ? `<div class="row small muted" style="flex-wrap:wrap;margin-bottom:var(--s3)">裝置版本 ${links.join('')}</div>` : '';
}

/**
 * Fetch and format a CSV artifact as an HTML table.
 * @param {string} dl Download URL
 * @returns {Promise<string>} Table HTML
 */
async function renderCsvTableHtml(dl) {
  const rows = parseCsv(await (await fetch(dl)).text()).filter(r => r.some(c => c.trim()));
  const [head, ...body] = rows;
  return `<div class="reader"><table><thead><tr>${(head || []).map(c => `<th>${escHtml(c)}</th>`).join('')}</tr></thead>
    <tbody>${body.map(r => `<tr>${r.map(c => `<td>${escHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

/* Mind map controls & style designer live in studio-mindmap-designer.js. */

/**
 * Show one document-like output inside the workbench (iframe, image, table or video by file type).
 * @param {string} kind Key of REPORT_KINDS
 * @returns {Promise<void>} Resolves when viewer content is rendered
 */
async function loadReportInViewer(kind) {
  if (!currentStudyCourse) return;
  const group = currentReportGroup.includes(kind) ? currentReportGroup : [kind];
  const kindBox = document.getElementById('reportKindButtons');
  kindBox.innerHTML = group.length > 1 ? group.map(key =>
    `<button type="button" class="reader-pill-btn${key === kind ? ' on' : ''}" onclick="loadReportInViewer(${jsAttr(key)})">${REPORT_KINDS[key].label}</button>`).join('') : '';
  const container = document.getElementById('reportContentContainer');
  const metaBar = document.getElementById('reportMetaBar');
  const spec = REPORT_KINDS[kind] || REPORT_KINDS.guide;
  const job = pickLatestJob(spec.types);
  if (!job) {
    if (metaBar) metaBar.innerHTML = '';
    container.innerHTML = `<div class="empty-state">${activeStudyLectureNo === null ? '整門課' : '這一講'}還沒有「${spec.label}」。<br>可到「批次排程」的「產出內容」勾選後生成。<br><button class="btn btn-soft" onclick="go('queue')">前往批次排程</button></div>`;
    return;
  }
  const code = currentStudyCourse.code, path = job.rel_path || job.output_file.split('/').pop(), enc = encodeURI(path);
  const dl = `/api/artifacts/${code}/download/${enc}`, readable = ['guide', 'concept'].includes(kind) && activeStudyLectureNo !== null;
  const ext = path.split('.').pop().toLowerCase();
  if (kind === 'mindmap' && ['json', 'opml'].includes(ext)) renderMindmapTools(kindBox);
  const metaHtml = `<span class="tag">v${job.version || 1}</span>${job.status === 'needs_review' ? '<span class="tag warn">需審查</span>' : ''}
    <a class="reader-pill-btn" href="${dl}" target="_blank" rel="noopener">新分頁 / 下載</a>${readable ? `<button type="button" class="reader-pill-btn" onclick="markStep('guide')">我讀完了</button>` : ''}`;
  if (metaBar) metaBar.innerHTML = metaHtml;
  if (['md', 'opml', 'json'].includes(ext)) container.innerHTML = `<iframe class="report-frame" src="/api/artifacts/${code}/view/${enc}" title="${escHtml(spec.label)}"></iframe>`;
  else if (ext === 'png') container.innerHTML = (await renderPngDeviceExtras(code, path)) + `<img class="report-img" src="${dl}" alt="${escHtml(spec.label)}">`;
  else if (ext === 'csv') container.innerHTML = await renderCsvTableHtml(dl);
  else if (['mp4', 'webm', 'mov'].includes(ext)) container.innerHTML = `<video class="report-video" controls preload="metadata" src="${dl}"></video>`;
  else if (ext === 'pdf' || ext === 'html') container.innerHTML = `<iframe class="report-frame" src="${dl}" title="${escHtml(spec.label)}"></iframe>`;
  else container.innerHTML = `<div class="empty-state">這個格式（.${escHtml(ext)}）無法在網頁預覽，請用上方連結下載。</div>`;
}
