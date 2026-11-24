/**
 * Learning record view, dynamic study layout options, term-grouped filtering, and course lifecycle UI flows (SPEC-014 Task 13).
 * Uses global helpers from studio-escape.js, studio-core.js, studio-app.js, and studio-batch.js.
 */

const _ROLE_LABELS = {
  materials: '課本 / 文獻',
  handouts: '老師教材',
  notes: '個人筆記',
  homework: '作業檔案',
  assignments: '期中 / 期末報告',
};

const _STATUS_BADGE = {
  active: { text: '修課中', cls: 'badge-success' },
  archived: { text: '已封存', cls: 'badge-neutral' },
  unregistered: { text: '未登錄', cls: 'badge-warning' },
};

let showArchivedCourses = typeof prefLoad === 'function' ? prefLoad('showArchived', 'false') === 'true' : false;

/**
 * Filter courses according to archive visibility preference, sorted by term and code.
 * @returns {Array<object>} Ordered visible course objects
 */
function visibleCoursesList() {
  const list = typeof currentCoursesList !== 'undefined' && currentCoursesList ? currentCoursesList : [];
  const filtered = showArchivedCourses ? list : list.filter(c => c.status !== 'archived');
  return [...filtered].sort((a, b) => String(b.term || '').localeCompare(String(a.term || '')) || String(a.code).localeCompare(String(b.code)));
}

/**
 * Toggle visibility of archived courses in top-bar picker and course directory.
 */
function toggleShowArchivedCourses() {
  showArchivedCourses = !showArchivedCourses;
  if (typeof prefSave === 'function') prefSave('showArchived', String(showArchivedCourses));
  if (typeof initStudyPortal === 'function') {
    const sel = document.getElementById('studyCourseSelect');
    if (sel) sel.innerHTML = renderTermCourseOptionsHtml(visibleCoursesList());
  }
  if (typeof renderCourseDirectory === 'function') renderCourseDirectory();
  if (typeof renderCoursePicker === 'function') renderCoursePicker();
}

/**
 * Render `<optgroup>` grouped `<option>` HTML for `#studyCourseSelect`.
 * @param {Array<object>} visible Filtered course objects
 * @returns {string} Option markup grouped by term
 */
function renderTermCourseOptionsHtml(visible) {
  const byTerm = new Map();
  visible.forEach(c => {
    const key = c.term || '其他';
    if (!byTerm.has(key)) byTerm.set(key, []);
    byTerm.get(key).push(c);
  });
  return [...byTerm.entries()].map(([term, list]) =>
    `<optgroup label="${escHtml(term)}">${list.map(c => `<option value="${escHtml(c.code)}">${escHtml(c.code)}　${escHtml(c.name)}${c.status === 'archived' ? '（已封存）' : ''}</option>`).join('')}</optgroup>`
  ).join('') || '<option value="">（無顯示中的課程）</option>';
}

/**
 * Render term-grouped course directory list with archived-visibility toggle button.
 * @param {Array<object>} filtered Filtered course list
 * @returns {string} Directory HTML markup
 */
function renderGroupedCourseDirectoryHtml(filtered) {
  const all = typeof currentCoursesList !== 'undefined' ? currentCoursesList : [];
  const archivedCount = all.filter(c => c.status === 'archived').length;
  const toggleHtml = archivedCount
    ? `<div style="padding:4px 0 8px"><button class="btn btn-ghost btn-sm" onclick="toggleShowArchivedCourses()">${showArchivedCourses ? '隱藏已封存課程' : `顯示已封存課程（${archivedCount}）`}</button></div>`
    : '';
  if (!filtered.length) {
    return toggleHtml + (all.length ? '<div class="empty-state">目前這個篩選分類下沒有課程。</div>' : '<div class="empty-state">還沒有課程。到「批次排程」按「加入課程」選講義資料夾。<br><button class="btn btn-soft" onclick="go(\'queue\')">前往批次排程</button></div>');
  }
  const byTerm = new Map();
  filtered.forEach(c => {
    const key = c.term || '其他';
    if (!byTerm.has(key)) byTerm.set(key, []);
    byTerm.get(key).push(c);
  });
  return toggleHtml + [...byTerm.entries()].map(([term, list]) =>
    `<div class="small muted" style="padding:6px 4px 2px;font-weight:600">${escHtml(term)}</div>` + list.map(c => {
      const stats = c.counts || {}, total = (c.total_jobs || 0) - (stats.skipped || 0);
      const pct = total > 0 ? Math.round(((stats.done || 0) / total) * 100) : 0;
      const on = typeof currentStudyCourse !== 'undefined' && currentStudyCourse && currentStudyCourse.code === c.code ? ' on' : '';
      return `<button class="course${on}" onclick="pickStudyCourse(${jsAttr(c.code)})"><span class="course-cover" style="background:${courseColour(c.code)}">${escHtml(String(c.code).slice(0, 3))}</span>
        <span style="min-width:0"><span class="course-name">${escHtml(c.name)}${c.status === 'archived' ? '（已封存）' : ''}</span><span class="small muted">${c.lecture_count} 講　·　產出完成 ${pct}%</span><span class="bar"><i style="width:${pct}%"></i></span></span></button>`;
    }).join('')
  ).join('');
}

/**
 * Format human-readable category display label from role and folder name.
 * @param {string} role Semantic category role
 * @param {string} name Folder display name
 * @returns {string} Annotated label
 */
function _formatCategoryLabel(role, name) {
  return `${name}${_ROLE_LABELS[role] ? `（${_ROLE_LABELS[role]}）` : ''}`;
}

/**
 * Load configured study folder categories from `/api/study/layout` and update literature menus.
 * @returns {Promise<void>}
 */
async function loadStudyLayoutOptions() {
  try {
    const res = await fetch('/api/study/layout');
    if (!res.ok) return;
    const data = await res.json();
    const roles = Array.isArray(data.roles) ? data.roles : [];
    const names = data.names || {};
    const list = roles.map(r => names[r]).filter(Boolean);
    if (!list.length) return;
    window.STUDY_CATEGORIES = list;
    const menu = document.getElementById('litCategoryMenu');
    const wrap = document.getElementById('litCategorySelectWrap');
    const txt = document.querySelector('#litCategoryBtn .lit-sel-txt');
    if (!menu || !wrap) return;
    const current = wrap.getAttribute('data-value') || list[0];
    const selected = list.includes(current) ? current : list[0];
    wrap.setAttribute('data-value', selected);
    menu.innerHTML = roles.map(r => {
      const name = names[r];
      if (!name) return '';
      const on = name === selected ? ' on' : '';
      return `<button type="button" class="lit-select-opt${on}" data-val="${escHtml(name)}">${escHtml(_formatCategoryLabel(r, name))}</button>`;
    }).join('');
    if (txt) txt.textContent = _formatCategoryLabel(roles.find(r => names[r] === selected), selected);
  } catch (e) {
    console.warn('Could not load study layout:', e);
  }
}

/**
 * Toggle archive state for a registered course cleanly via HTTP and refresh UI lists.
 * @param {string} code Course code
 * @param {boolean} archived True to archive, false to restore
 * @returns {Promise<void>}
 */
async function toggleCourseArchived(code, archived) {
  const endpoint = archived ? 'archive' : 'restore';
  try {
    const res = await fetch(`/api/courses/${encodeURIComponent(code)}/${endpoint}`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || '無法變更封存狀態');
    showToast(archived ? `已封存課程 ${code}` : `已恢復課程 ${code}`, 'success');
    await fetchCourses();
    if (activeCourseCode === code && typeof viewCourseDetail === 'function') await viewCourseDetail(code);
    if (typeof initStudyPortal === 'function') await initStudyPortal();
  } catch (e) {
    showToast(e.message || '變更封存失敗', 'error');
  }
}

/**
 * Format dry-run impact confirmation text for the course rename two-step dialog.
 * @param {string} code Previous course code
 * @param {string} newCode Replacement course code
 * @param {object} preview Dry-run JSON payload from `/rename`
 * @returns {string} Confirmation prompt text
 */
function _formatRenameConfirmMessage(code, newCode, preview) {
  const tablesSummary = Object.entries(preview.tables || {})
    .filter(([, n]) => n > 0)
    .map(([t, n]) => `${t}: ${n}`)
    .join('、') || '0 筆關聯紀錄';
  const filesSummary = Object.entries(preview.files || {})
    .filter(([, n]) => n > 0)
    .map(([f, n]) => `${f}: ${n}`)
    .join('、') || '0 個檔案';
  return (
    `【改代碼預覽（Dry-Run）】\n舊代碼：${code} → 新代碼：${newCode}\n\n` +
    `資料庫資料表：${tablesSummary}\n本機檔案／資料夾：${filesSummary}\n\n` +
    '確定要正式執行改代碼嗎？'
  );
}

/**
 * Run a two-step dry-run-first course rename flow before committing DB and file changes.
 * @param {string} code Existing course code
 * @returns {Promise<void>}
 */
async function openRenameCourseFlow(code) {
  const input = window.prompt(`請輸入「${code}」的新課程代碼（例：115-1_CP31000）：`, code);
  if (!input || !input.trim() || input.trim() === code) return;
  const newCode = input.trim();
  try {
    const dryRes = await fetch(`/api/courses/${encodeURIComponent(code)}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_code: newCode, dry_run: true }),
    });
    const preview = await dryRes.json().catch(() => ({}));
    if (!dryRes.ok) throw new Error(preview.detail || '無法預覽改代碼影響範圍');
    if (!window.confirm(_formatRenameConfirmMessage(code, newCode, preview))) return;
    const applyRes = await fetch(`/api/courses/${encodeURIComponent(code)}/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_code: newCode, dry_run: false }),
    });
    const applied = await applyRes.json().catch(() => ({}));
    if (!applyRes.ok) throw new Error(applied.detail || '改代碼失敗');
    showToast(`課程代碼已安全更新為 ${newCode}`, 'success');
    if (activeCourseCode === code) activeCourseCode = newCode;
    await fetchCourses();
    if (typeof viewCourseDetail === 'function') await viewCourseDetail(newCode);
    if (typeof initStudyPortal === 'function') await initStudyPortal();
  } catch (e) {
    showToast(e.message || '改代碼失敗', 'error');
  }
}

/**
 * Update export download hrefs to match active term filter in the learning record view.
 * @param {string} term Selected semester filter or ''
 */
function _syncRecordExportLinks(term) {
  const qs = term ? `term=${encodeURIComponent(term)}&` : '';
  const mdLink = document.getElementById('recordExportMd');
  const pdfLink = document.getElementById('recordExportPdf');
  if (mdLink) mdLink.href = `/api/study/record/export?${qs}format=md`;
  if (pdfLink) pdfLink.href = `/api/study/record/export?${qs}format=pdf`;
}

/**
 * Render one course card inside a term block of 學習紀錄.
 * @param {object} course CourseRecordView payload
 * @returns {string} HTML string
 */
function _recordCourseHtml(course) {
  const badge = _STATUS_BADGE[course.status] || { text: course.status, cls: 'badge-neutral' };
  const s = course.stats || {};
  const cats = (course.categories || []).map(cat => {
    const fileList = (cat.files || []).map(f => `<li class="small">${escHtml(f)}</li>`).join('');
    return `<details class="rec-cat"><summary>${escHtml(cat.role)}（${(cat.files || []).length}）</summary><ul>${fileList}</ul></details>`;
  }).join('');
  return `<article class="card rec-course" style="margin-bottom:12px">
    <div class="card-head">
      <div><b>${escHtml(course.name)}</b> <span class="small muted num">${escHtml(course.code)}</span></div>
      <span class="badge ${badge.cls}">${escHtml(badge.text)}</span>
    </div>
    <div class="rec-stats small muted num" style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px">
      <span>講次 ${s.lectures || 0}</span>
      <span>已完成產出 ${s.artifacts_done || 0}</span>
      <span>測驗 ${s.quiz_attempts || 0} 次（最高 ${s.quiz_best_score || 0}%）</span>
      <span>待解錯題 ${s.mistakes_open || 0}</span>
      <span>問答筆記 ${s.qa_notes || 0}</span>
      <span>文獻 ${s.literature || 0}</span>
      <span>學習 ${s.study_days || 0} 天 / 約 ${s.study_minutes || 0} 分</span>
      <span>記憶強度 ${s.memory_strength_avg || 0}%</span>
    </div>
    ${cats || '<div class="small muted">尚無分類檔案</div>'}
  </article>`;
}

/**
 * Fetch and render cross-term learning record views into `#view-record`.
 * @param {string} [term=''] Optional semester filter
 * @returns {Promise<void>}
 */
async function loadLearningRecordView(term) {
  const filterSel = document.getElementById('recordTermFilter');
  const chosen = term !== undefined ? term : (filterSel ? filterSel.value : '');
  _syncRecordExportLinks(chosen);
  const host = document.getElementById('recordContent');
  if (!host) return;
  try {
    const url = chosen ? `/api/study/record?term=${encodeURIComponent(chosen)}` : '/api/study/record';
    const res = await fetch(url);
    if (!res.ok) throw new Error('無法載入學習紀錄');
    const data = await res.json();
    const terms = data.terms || [];
    if (filterSel && !chosen) {
      const prev = filterSel.value;
      filterSel.innerHTML = '<option value="">全部學期</option>' +
        terms.map(t => `<option value="${escHtml(t.term)}">${escHtml(t.term)}</option>`).join('');
      if (prev) filterSel.value = prev;
    }
    if (!terms.length) {
      host.innerHTML = '<div class="card empty-state">目前尚無學期課程與學習紀錄。</div>';
      return;
    }
    host.innerHTML = terms.map(t => {
      const others = (t.others || []).length
        ? `<div class="small muted" style="margin-top:6px">其他資料夾／檔案：${t.others.map(escHtml).join('、')}</div>`
        : '';
      return `<section class="rec-term" style="margin-bottom:20px">
        <h2 class="h2" style="margin-bottom:10px">${escHtml(t.term)}</h2>
        ${(t.courses || []).map(_recordCourseHtml).join('') || '<div class="small muted">此學期尚無課程</div>'}
        ${others}
      </section>`;
    }).join('');
  } catch (e) {
    host.innerHTML = `<div class="card empty-state">${escHtml(e.message || '載入失敗')}</div>`;
  }
}

/**
 * Fetch and display the read-only three-profile sign-in status list inside `#signInStatusList`.
 * @returns {Promise<void>}
 */
async function loadSignInStatus() {
  const host = document.getElementById('signInStatusList');
  if (!host) return;
  try {
    const res = await fetch('/api/system/sign-ins');
    if (!res.ok) throw new Error('無法取得登入狀態');
    const data = await res.json();
    const stateBadge = {
      ready: { text: '就緒', cls: 'badge-success' },
      expired: { text: '已過期', cls: 'badge-warning' },
      missing: { text: '尚未登入', cls: 'badge-neutral' },
    };
    host.innerHTML = (data.sign_ins || []).map(item => {
      const b = stateBadge[item.state] || { text: item.state, cls: 'badge-neutral' };
      return `<div class="row" style="justify-content:space-between;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--border);gap:12px">
        <div style="min-width:0">
          <div><b>${escHtml(item.name)}</b> <span class="badge ${b.cls}">${escHtml(b.text)}</span></div>
          <div class="small muted num" style="word-break:break-all">${escHtml(item.location)}</div>
          <div class="small muted">${escHtml(item.how_to_sign_in)}</div>
        </div>
      </div>`;
    }).join('') || '<div class="small muted">尚無登入設定項目。</div>';
  } catch (e) {
    host.innerHTML = `<div class="small muted">${escHtml(e.message || '載入失敗')}</div>`;
  }
}

window.loadStudyLayoutOptions = loadStudyLayoutOptions;
window.loadLearningRecordView = loadLearningRecordView;
window.loadSignInStatus = loadSignInStatus;
window.toggleCourseArchived = toggleCourseArchived;
window.openRenameCourseFlow = openRenameCourseFlow;
