/**
 * Gemini Notebook 學習工作室 — add-course wizard (folder picker, preview estimates, defaults, and submission).
 * Loaded immediately after studio-settings.js (relies on OPTION_LABELS, COURSE_FIELD_LABELS,
 * renderOptionField, collectOptions, getSelectedArtifacts, escHtml, showToast, wizardGo, fetchStatus, fetchCourses, initStudyPortal).
 */

/** Open the add-course modal, load folder browser and default options, and jump to step 1. */
function openAddModal() {
  document.getElementById('addModal').style.display = 'flex';
  browseFolder(null);
  loadAddOptions();
  wizardGo(1);
}

let currentBrowsePath = null;
let currentBrowseParent = null;
let pickedFolders = [];

/**
 * Show the sub-folders of a folder (the start location when path is null).
 * @param {string|null} path Folder path
 * @returns {Promise<void>} Resolves when folder listing is rendered
 */
async function browseFolder(path) {
  const list = document.getElementById('folderList');
  try {
    const res = await fetch('/api/folders' + (path ? `?path=${encodeURIComponent(path)}` : ''));
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    currentBrowsePath = data.path;
    currentBrowseParent = data.parent;
    document.getElementById('folderCurrent').textContent = data.path ? `${data.path}（${data.pdf_count} 個 PDF）` : '從這裡開始找課程資料夾';
    document.getElementById('btnFolderUp').disabled = !data.parent;
    document.getElementById('btnPickFolder').disabled = !data.path || data.pdf_count === 0;
    list.innerHTML = data.folders.length ? data.folders.map((f, i) => `
      <div class="folder-item">
        <button type="button" data-idx="${i}" class="folder-open"><i class="icon-folder"></i>${escHtml(f.name)} ${f.pdf_count ? `<span class="badge badge-success">${f.pdf_count} 個 PDF</span>` : ''}</button>
        ${f.pdf_count ? `<button type="button" data-idx="${i}" class="folder-pick btn btn-soft btn-sm">選</button>` : ''}
      </div>`).join('') : '<p class="small muted">（這裡沒有子資料夾）</p>';
    list.querySelectorAll('.folder-open').forEach(b => { b.onclick = () => browseFolder(data.folders[b.dataset.idx].path); });
    list.querySelectorAll('.folder-pick').forEach(b => { b.onclick = () => addPickedFolder(data.folders[b.dataset.idx].path); });
  } catch (e) {
    list.innerHTML = `<p style="color:var(--danger)">無法開啟：${escHtml(e.message)}</p>`;
  }
}

/** Pick the folder being shown. */
function pickCurrentFolder() {
  if (currentBrowsePath) addPickedFolder(currentBrowsePath);
}

/**
 * Add a course folder to the picks.
 * @param {string} path Folder path
 */
function addPickedFolder(path) {
  if (!pickedFolders.includes(path)) pickedFolders.push(path);
  renderPickedFolders();
}

/**
 * Remove one picked folder.
 * @param {number} idx Index in the picks
 */
function removePickedFolder(idx) {
  pickedFolders.splice(idx, 1);
  renderPickedFolders();
}

/**
 * Infer default term, course number, and course name from a picked folder path.
 * @param {string} folderPath Selected folder path
 */
function prefillCourseIdentityFromPath(folderPath) {
  const parts = String(folderPath || '').replace(/\\/g, '/').split('/').filter(Boolean);
  const base = parts[parts.length - 1] || '';
  const parent = parts[parts.length - 2] || '';
  const termEl = document.getElementById('addTerm');
  const noEl = document.getElementById('addCourseNo');
  const nameEl = document.getElementById('addCourseName');
  if (!termEl || !noEl || !nameEl) return;
  if (!termEl.value && /^\d{2,4}-\d{1,2}$/.test(parent)) termEl.value = parent;
  const m = base.match(/^([A-Za-z]{1,6})_{1,2}([0-9A-Za-z]+)-(.+)$/);
  if (m) {
    if (!noEl.value) noEl.value = `${m[1]}${m[2]}`.toUpperCase();
    if (!nameEl.value) nameEl.value = m[3];
  } else if (!nameEl.value) {
    nameEl.value = base;
  }
}

/** Draw the picked folders. */
function renderPickedFolders() {
  document.getElementById('folderPaths').value = pickedFolders.join('\n');
  document.getElementById('btnConfirmAdd').disabled = true;
  if (pickedFolders.length === 1) prefillCourseIdentityFromPath(pickedFolders[0]);
  document.getElementById('pickedFolders').innerHTML = pickedFolders.length ? pickedFolders.map((p, i) =>
    `<span class="badge">${escHtml(p.split('/').pop())}<button type="button" onclick="removePickedFolder(${i})" aria-label="移除">✕</button></span>`).join('')
    : '<span class="muted small">（還沒選）</span>';
}

/** Close the wizard and forget the picks. */
function closeAddModal() {
  document.getElementById('addModal').style.display = 'none';
  document.getElementById('previewResults').style.display = 'none';
  ['addTerm', 'addCourseNo', 'addCourseName'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  pickedFolders = [];
  renderPickedFolders();
}

/**
 * Estimate lectures, jobs and quota for the picked folders.
 * @returns {Promise<void>} Resolves when preview HTML is rendered
 */
async function previewFolders() {
  const folders = document.getElementById('folderPaths').value.split('\n').map(s => s.trim()).filter(Boolean);
  if (folders.length === 0) {
    showToast('請先點選至少一個課程資料夾', 'warning');
    return;
  }
  const { chapterArts, courseArts } = getSelectedArtifacts();
  try {
    const res = await fetch('/api/courses/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folders, chapter_artifacts: chapterArts, course_artifacts: courseArts }),
    });
    const results = await res.json();
    const box = document.getElementById('previewResults');
    box.style.display = 'block';
    box.innerHTML = results.map(r => `
      <div style="margin-bottom:8px">
        <strong>${r.is_valid ? escHtml(r.course_code + '（' + r.course_name + '）') : '無效資料夾'}</strong>
        <div>${r.is_valid ? '掃描到 ' + r.lecture_count + ' 講，依目前勾選預估 ' + r.estimated_jobs + ' 項工作' + (r.quota_estimate_available ? '，約用 ' + r.estimated_quota_percent + '% 的 5 小時額度（目前剩 ' + r.five_hour_remaining_percent + '%）' + (r.estimated_wait_hours > 0 ? '，需等額度重置約 ' + r.estimated_wait_hours + ' 小時' : '，目前額度足夠') + (r.weekly_remaining_percent !== null ? '；本週額度剩 ' + r.weekly_remaining_percent + '%' : '') + (r.weekly_warning ? '<br>' + escHtml(r.weekly_warning) : '') : '（無法讀取額度，未估算時間）') : escHtml(r.error)}</div>
      </div>`).join('');
    document.getElementById('btnConfirmAdd').disabled = !results.some(r => r.is_valid);
  } catch (e) {
    showToast('預覽失敗：' + e.message, 'error');
  }
}

let addDefaults = null;

/**
 * Draw the advanced settings of the wizard (project defaults).
 * @returns {Promise<void>} Resolves when wizard option fields are rendered
 */
async function loadAddOptions() {
  const box = document.getElementById('addOptions');
  try {
    const data = await (await fetch('/api/generation-options')).json();
    addDefaults = data.defaults;
    const all = { mock_exam_questions: COURSE_FIELD_LABELS.mock_exam_questions, ...OPTION_LABELS };
    box.innerHTML = `<div class="settings-grid">
      ${Object.keys(all).map(key => renderOptionField(key, all[key], { value: data.defaults[key], choices: data.choices, defaults: data.defaults })).join('')}
    </div>`;
  } catch (e) {
    box.innerHTML = `<p style="color:var(--danger)">載入失敗：${escHtml(e.message)}</p>`;
  }
}

/**
 * Only the wizard settings that differ from the defaults (untouched ones stay on the project defaults).
 * @returns {object|null} Changed options or null
 */
function changedAddOptions() {
  if (!addDefaults || !document.getElementById('addOptions').querySelector('[data-opt]')) return null;
  const picked = collectOptions('#addOptions');
  const changed = Object.fromEntries(Object.entries(picked).filter(([k, v]) => v !== addDefaults[k]));
  return Object.keys(changed).length ? changed : null;
}

/**
 * Register the picked folders as courses (and start the queue when asked).
 * @returns {Promise<void>} Resolves after creating courses
 */
async function confirmAddFolders() {
  const folders = document.getElementById('folderPaths').value.split('\n').map(s => s.trim()).filter(Boolean);
  const { chapterArts, courseArts, language } = getSelectedArtifacts();
  const autoStart = document.getElementById('autoStartQueue').checked;
  const reuseNotebook = document.getElementById('reuseNotebook').checked;
  try {
    const res = await fetch('/api/courses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        folders,
        profile: 'full',
        chapter_artifacts: chapterArts,
        course_artifacts: courseArts,
        language,
        paused: !autoStart,
        reuse_notebook: reuseNotebook,
        options: changedAddOptions(),
        term: (document.getElementById('addTerm')?.value || '').trim(),
        course_no: (document.getElementById('addCourseNo')?.value || '').trim(),
        course_name: (document.getElementById('addCourseName')?.value || '').trim(),
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    if (autoStart) await fetch('/api/queue/start', { method: 'POST' });
    showToast(autoStart ? '已加入課程，開始自動生成。' : '已加入課程並暫停。確認設定後按「開始生成」。', 'success');
    closeAddModal();
    await fetchStatus();
    await fetchCourses();
    await initStudyPortal();
  } catch (e) {
    showToast('加入失敗：' + e.message, 'error');
  }
}
