/* Gemini Notebook 學習工作室 — settings forms and dialogs: course settings (with the exam date), which outputs
   a course generates, one output's own settings, prompt editor, naming rules, usage guide, and the
   add-course wizard (folder picker, presets, estimate, confirm).
   Uses globals from studio-app.js / studio-batch.js (escHtml, hueFor, viewCourseDetail, fetchCourses,
   fetchStatus, initStudyPortal, loadTodayPanel). */

/** Labels for every generation option: [label, choice names | 'number' | 'text' | 'textarea' | null (yes/no)]. */
const OPTION_LABELS = {
  infographic_orientation: ['資訊圖表方向', { landscape: '橫式', portrait: '直式（A4 / iPad）', square: '方形' }],
  infographic_detail: ['資訊圖表詳細程度', { concise: '精簡', standard: '標準', detailed: '詳細' }],
  infographic_style: ['資訊圖表風格', { auto_select: '自動', sketch_note: '手繪筆記', professional: '專業', bento_grid: '便當格', editorial: '雜誌', instructional: '教學', bricks: '積木', clay: '黏土', anime: '動漫', kawaii: '可愛', scientific: '科學' }],
  device_exports: ['資訊圖表另存裝置版本（A4 PDF / iPad Air 4 / MacBook Pro 14）', null],
  audio_format: ['語音形式', { deep_dive: '深度對談', brief: '簡短摘要', critique: '評論', debate: '辯論' }],
  audio_length: ['語音長度', { short: '短', default: '標準', long: '長' }],
  slide_format: ['投影片形式', { detailed_deck: '詳細版（自學）', presenter_slides: '講者版（上台）' }],
  slide_length: ['投影片長度', { default: '標準', short: '精簡' }],
  slide_download: ['投影片下載格式', { pdf: 'PDF', pptx: 'PowerPoint (PPTX)' }],
  video_format: ['影片形式', { explainer: '講解', brief: '簡短', short: '直式短片' }],
  video_style: ['影片風格', { auto_select: '自動', classic: '經典', whiteboard: '白板', kawaii: '可愛', anime: '動漫', watercolor: '水彩', retro_print: '復古印刷', heritage: '傳統', paper_craft: '紙藝' }],
  quiz_questions: ['每份測驗題數（10–60）', 'number'],
  flashcards_quantity: ['學習卡數量', { fewer: '較少', standard: '標準', more: '較多' }],
  flashcards_difficulty: ['學習卡難度', { easy: '簡單', medium: '中等', hard: '困難' }],
  quiz_difficulty: ['測驗難度', { auto: '依測驗而定（1 簡單、2 中等、3 困難）', easy: '全部簡單', medium: '全部中等', hard: '全部困難' }],
  video_style_prompt: ['影片自訂風格描述（填了就用這段描述，直式短片不適用）', 'text'],
  chapter_range: ['整門課產出涵蓋的講次（例如 1-3 或 1,3,5-6；留空＝全部）', 'text'],
  extra_instructions: ['補充指示（加在每一份產出的要求後面，例如「考試以申論題為主」）', 'textarea'],
};
/** Course-only fields shown at the top of the course settings. */
const COURSE_FIELD_LABELS = {
  language: ['產出語言', { 'zh-TW': '繁體中文', en: 'English', bilingual: '中英雙語' }],
  exam_date: ['考試日期（用於複習計畫與倒數）', 'date'],
  mock_exam_questions: ['全課程模擬考題數（10–100）', 'number'],
};

/**
 * HTML for one settings field.
 * @param {string} key Option key
 * @param {string} label Label
 * @param {object|string|null} names Choice names, a field kind ('number' | 'text' | 'textarea' | 'date') or null for yes/no
 * @param {*} value Current value
 * @param {object} choices Allowed values per key
 * @param {string} [inherit] Inherited value (shown as the "use course setting" option)
 * @param {object} [defaults] Default values per key
 * @returns {string} HTML
 */
function renderOptionField(key, label, names, value, choices, inherit, defaults) {
  const dflt = defaults ? defaults[key] : undefined;
  const mark = v => (dflt !== undefined && v === dflt ? '（預設）' : '');
  const inheritOpt = inherit !== undefined ? `<option value="">沿用課程設定（${escHtml(String(inherit))}）</option>` : '';
  if (names === null) {
    if (inherit !== undefined) {
      return `<label class="opt-field"><span>${label}</span><select class="select" data-opt="${key}">${inheritOpt}
        <option value="true" ${value === true ? 'selected' : ''}>是${mark(true)}</option><option value="false" ${value === false ? 'selected' : ''}>否${mark(false)}</option></select></label>`;
    }
    return `<label class="cbox span-all"><input type="checkbox" data-opt="${key}" ${value ? 'checked' : ''}>${label}${dflt !== undefined ? `（預設：${dflt ? '開' : '關'}）` : ''}</label>`;
  }
  if (names === 'textarea') {
    return `<label class="opt-field span-all"><span>${label}</span><textarea class="text-area" data-opt="${key}" rows="2" placeholder="${inherit !== undefined ? '留空就只用課程的補充指示' : '例如：考試以申論題為主；重點放在第 3 章的公式'}">${escHtml(value || '')}</textarea>
      <span class="hint">不會取代原本的 Prompt，而是加在最後（「補充要求：…」）。</span></label>`;
  }
  if (names === 'text') {
    return `<label class="opt-field"><span>${label}</span><input type="text" class="text-input wide" data-opt="${key}" value="${escHtml(value || '')}"></label>`;
  }
  if (names === 'date') {
    return `<label class="opt-field"><span>${label}</span><input type="date" class="text-input wide" data-opt="${key}" value="${escHtml(value || '')}"></label>`;
  }
  if (names === 'number') {
    const range = choices[key] || {};
    return `<label class="opt-field"><span>${label}${dflt !== undefined ? `（預設 ${dflt}）` : ''}</span><input type="number" class="text-input wide" min="${range.min ?? ''}" max="${range.max ?? ''}" data-opt="${key}" data-num="1" value="${value ?? ''}" placeholder="${inherit !== undefined ? '留空就沿用課程設定' : ''}"></label>`;
  }
  const opts = (choices[key] || []).map(c => `<option value="${c}" ${c === value ? 'selected' : ''}>${names[c] || c}${mark(c)}</option>`).join('');
  return `<label class="opt-field"><span>${label}</span><select class="select" data-opt="${key}">${inheritOpt}${opts}</select></label>`;
}

/**
 * Read every settings field inside a container.
 * @param {string} selector CSS selector of the container
 * @returns {object} Option values by key
 */
function collectOptions(selector) {
  const options = {};
  document.querySelectorAll(`${selector} [data-opt]`).forEach(el => {
    let v = el.type === 'checkbox' ? el.checked : el.value;
    if (el.dataset.num) v = v === '' ? '' : parseInt(v, 10);
    if (el.tagName === 'SELECT' && (v === 'true' || v === 'false')) v = v === 'true';
    options[el.dataset.opt] = v;
  });
  return options;
}

/**
 * Draw the course settings form.
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function loadCourseOptions(code) {
  const box = document.getElementById('detailOptions');
  try {
    const res = await fetch(`/api/courses/${code}/options`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const all = { ...COURSE_FIELD_LABELS, ...OPTION_LABELS };
    box.innerHTML = `<div class="settings-grid">
        ${Object.keys(all).map(key => renderOptionField(key, all[key][0], all[key][1], data.options[key], data.choices, undefined, data.defaults)).join('')}
      </div>
      <div class="sec-foot"><button type="button" class="btn btn-ghost" onclick="resetCourseOptions('${code}')">全部恢復預設值</button><button class="btn btn-primary" onclick="saveCourseOptions('${code}')">儲存課程設定</button></div>`;
  } catch (e) {
    box.innerHTML = `<p style="color:var(--danger)">設定載入失敗：${escHtml(e.message)}</p>`;
  }
}

/**
 * Draw which outputs the course generates.
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function loadArtifactSelection(code) {
  const box = document.getElementById('detailSelection');
  try {
    const res = await fetch(`/api/courses/${code}/artifact-types`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    /**
     * One group of output checkboxes.
     * @param {string} scope 'chapter' or 'course'
     * @param {string} title Group title
     * @returns {string} HTML
     */
    const grid = (scope, title) => `<div class="check-group" style="margin-bottom:var(--s3)"><span class="field-label">${title}</span><div class="checks">
        ${data.choices[scope].map(c => `<label class="cbox" style="--hue:var(${hueFor(c.value)})"><input type="checkbox" data-scope="${scope}" value="${c.value}" ${data[scope].includes(c.value) ? 'checked' : ''}><span class="hue-dot"></span>${escHtml(c.label)}</label>`).join('')}
      </div></div>`;
    box.innerHTML = grid('chapter', '每份 PDF 各自生成') + grid('course', '全部 PDF 整合生成（整門課）') +
      `<div class="sec-foot"><button class="btn btn-primary" onclick="saveArtifactSelection('${code}')">儲存產出內容</button></div>`;
  } catch (e) {
    box.innerHTML = `<p style="color:var(--danger)">載入失敗：${escHtml(e.message)}</p>`;
  }
}

/**
 * Save which outputs the course generates (new ones are queued, removed ones skipped).
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function saveArtifactSelection(code) {
  const pick = scope => [...document.querySelectorAll(`#detailSelection input[data-scope="${scope}"]:checked`)].map(b => b.value);
  try {
    const res = await fetch(`/api/courses/${code}/artifact-types`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chapter: pick('chapter'), course: pick('course') }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast(`已儲存：新排入 ${data.queued + data.revived} 項、取消 ${data.skipped} 項尚未開始的工作。已完成的檔案都保留。`, 'success');
    await viewCourseDetail(code, true);
  } catch (e) {
    showToast('儲存失敗：' + e.message, 'error');
  }
}

/**
 * Put every course setting back to the default after confirmation.
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function resetCourseOptions(code) {
  if (!(await askConfirm('把這門課的設定全部恢復成預設值？', { okLabel: '恢復預設' }))) return;
  const data = await (await fetch(`/api/courses/${code}/options`)).json();
  await fetch(`/api/courses/${code}/options`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ options: data.defaults }),
  });
  await loadCourseOptions(code);
}

/**
 * Save the course settings (they apply to outputs generated afterwards).
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function saveCourseOptions(code) {
  const options = collectOptions('#detailOptions');
  try {
    const res = await fetch(`/api/courses/${code}/options`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ options }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast('已儲存。之後生成的內容會套用新設定；已生成的內容可按「重新生成」。', 'success');
    if (currentStudyCourse && currentStudyCourse.code === code) loadTodayPanel();
  } catch (e) {
    showToast('儲存失敗：' + e.message, 'error');
  }
}

/** Show the naming rules. */
async function openNamingModal() {
  document.getElementById('namingModal').style.display = 'flex';
  const box = document.getElementById('namingContent');
  try {
    const data = await (await fetch('/api/naming-guide')).json();
    box.innerHTML = `<ul style="margin:0 0 12px 20px;line-height:1.8">${data.rules.map(r => `<li>${escHtml(r)}</li>`).join('')}</ul>
      <table><thead><tr><th>代碼</th><th>名稱</th><th>意思</th><th>Gemini Notebook 標題</th><th>本機檔名</th></tr></thead><tbody>
      ${data.artifacts.map(a => `<tr><td><code>${a.artifact_type}</code></td><td>${escHtml(a.label)}</td><td>${escHtml(a.meaning)}</td><td><code>${escHtml(a.notebooklm_title)}</code></td><td><code>${escHtml(a.local_files)}</code></td></tr>`).join('')}
      </tbody></table>`;
  } catch (e) {
    box.innerHTML = `<p style="color:var(--danger)">載入失敗：${escHtml(e.message)}</p>`;
  }
}

/**
 * Open the settings of one output.
 * @param {string} jobId Job id
 * @returns {Promise<void>}
 */
async function openJobOptions(jobId) {
  document.getElementById('jobOptionsModal').style.display = 'flex';
  const box = document.getElementById('jobOptionsContent');
  box.innerHTML = '<p class="loading-line">載入中…</p>';
  try {
    const res = await fetch(`/api/jobs/${jobId}/options`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    document.getElementById('jobOptionsTitle').textContent = `${data.label} 的設定`;
    /**
     * Readable text for an inherited value (shown in the 沿用課程設定 option).
     * @param {string} key Option key
     * @param {*} v Value
     * @returns {string} Text
     */
    const describe = (key, v) => {
      const names = OPTION_LABELS[key] ? OPTION_LABELS[key][1] : null;
      if (typeof v === 'boolean') return v ? '是' : '否';
      if (names && typeof names === 'object') return names[v] || v;
      return v || '無';
    };
    box.innerHTML = `<div class="settings-grid">
        ${data.fields.map(key => {
          const [label, names] = OPTION_LABELS[key];
          const inherit = key === 'extra_instructions' ? '' : describe(key, data.effective[key]);
          return renderOptionField(key, label, names, data.overrides[key], data.choices, inherit, data.defaults);
        }).join('')}
      </div>
      ${data.unsupported.map(u => `<p class="hint" style="margin-top:10px">${escHtml(u)}</p>`).join('')}`;
    document.getElementById('btnSaveJobOptions').onclick = () => saveJobOptions(jobId);
  } catch (e) {
    box.innerHTML = `<p style="color:var(--danger)">載入失敗：${escHtml(e.message)}</p>`;
  }
}

/**
 * Save the settings of one output.
 * @param {string} jobId Job id
 * @returns {Promise<void>}
 */
async function saveJobOptions(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}/options`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ options: collectOptions('#jobOptionsContent') }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    document.getElementById('jobOptionsModal').style.display = 'none';
    showToast('已儲存這一份產出的設定', 'success', 2400);
    if (activeCourseCode) await viewCourseDetail(activeCourseCode, true);
  } catch (e) {
    showToast('儲存失敗：' + e.message, 'error');
  }
}

/** Show the usage guide. */
async function openUsageModal() {
  document.getElementById('usageModal').style.display = 'flex';
  const box = document.getElementById('usageContent');
  try {
    const data = await (await fetch('/api/usage-guide')).json();
    const note = data.note ? `<p class="plan-card small" style="margin-bottom:8px">${escHtml(data.note)}</p>` : '';
    box.innerHTML = note + data.sections.map(sec => `
      <h4 class="h2" style="margin:16px 0 6px">${escHtml(sec.heading)}</h4>
      <ol>${sec.steps.map(st => `<li>${escHtml(st)}</li>`).join('')}</ol>`).join('');
  } catch (e) {
    box.innerHTML = `<p style="color:var(--danger)">載入失敗：${escHtml(e.message)}</p>`;
  }
}

/** Close the usage guide. */
function closeUsageModal() {
  document.getElementById('usageModal').style.display = 'none';
}

/** Close the naming rules. */
function closeNamingModal() {
  document.getElementById('namingModal').style.display = 'none';
}

/** Hide the course detail on the batch page. */
function closeDetail() {
  document.getElementById('courseDetailSection').style.display = 'none';
}

/**
 * Open the prompt editor for one job.
 * @param {string} jobId Job id
 * @param {string} desc Short description for the title
 * @returns {Promise<void>}
 */
async function openPromptEditor(jobId, desc) {
  activeJobId = jobId;
  document.getElementById('promptModalTitle').textContent = `編輯 Prompt：${desc}`;
  document.getElementById('promptModalDesc').textContent = '這段指令會在向 Gemini Notebook 生成這份產出時送出。留空就用內建的指令；補充指示不受影響，仍會加在最後。';
  document.getElementById('promptModal').style.display = 'flex';
  try {
    const res = await fetch(`/api/jobs/${jobId}/prompt`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    document.getElementById('promptInput').value = data.custom_prompt || '';
  } catch (e) {
    document.getElementById('promptInput').value = '';
  }
}

/** Close the prompt editor. */
function closePromptModal() {
  document.getElementById('promptModal').style.display = 'none';
  activeJobId = null;
}

/** Save the prompt in the editor. */
async function savePrompt() {
  if (!activeJobId) return;
  const prompt = document.getElementById('promptInput').value;
  try {
    const res = await fetch(`/api/jobs/${activeJobId}/prompt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });
    if (!res.ok) throw new Error('儲存失敗');
    showToast('Prompt 已儲存', 'success', 2400);
    closePromptModal();
  } catch (e) {
    showToast('儲存失敗：' + e.message, 'error');
  }
}

/* ================= Add-course wizard ================= */

/**
 * Tick a preset set of outputs in the wizard.
 * @param {string} name 'full' | 'dual' | 'quiz'
 */
function setPreset(name) {
  const chapBoxes = document.querySelectorAll('input[name="chap_art"]');
  const courseBoxes = document.querySelectorAll('input[name="course_art"]');
  if (name === 'full') {
    // Video is the most expensive output (~10% of the 5-hour quota each); tick it by hand when needed.
    chapBoxes.forEach(b => { b.checked = b.value !== 'video'; });
    courseBoxes.forEach(b => { b.checked = b.value !== 'course_video'; });
  } else if (name === 'dual') {
    const dualCh = ['audio', 'quiz_1', 'quiz_2', 'quiz_3', 'study_guide', 'flashcards', 'mind_map', 'infographic', 'reports_concept_explanation'];
    const dualCo = ['course_mock_exam', 'course_mind_map', 'course_audio'];
    chapBoxes.forEach(b => { b.checked = dualCh.includes(b.value); });
    courseBoxes.forEach(b => { b.checked = dualCo.includes(b.value); });
  } else if (name === 'quiz') {
    chapBoxes.forEach(b => { b.checked = ['quiz_1', 'quiz_2', 'quiz_3', 'flashcards'].includes(b.value); });
    courseBoxes.forEach(b => { b.checked = b.value === 'course_mock_exam'; });
  }
}

/**
 * The outputs and language picked in the wizard.
 * @returns {{chapterArts: Array<string>, courseArts: Array<string>, language: string}} Picks
 */
function getSelectedArtifacts() {
  const chapterArts = Array.from(document.querySelectorAll('input[name="chap_art"]:checked')).map(el => el.value);
  const courseArts = Array.from(document.querySelectorAll('input[name="course_art"]:checked')).map(el => el.value);
  return { chapterArts, courseArts, language: document.getElementById('courseLanguage').value };
}

/** Open the add-course wizard at step 1. */
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
 * @returns {Promise<void>}
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

/** Draw the picked folders. */
function renderPickedFolders() {
  document.getElementById('folderPaths').value = pickedFolders.join('\n');
  document.getElementById('btnConfirmAdd').disabled = true;
  document.getElementById('pickedFolders').innerHTML = pickedFolders.length ? pickedFolders.map((p, i) =>
    `<span class="badge">${escHtml(p.split('/').pop())}<button type="button" onclick="removePickedFolder(${i})" aria-label="移除">✕</button></span>`).join('')
    : '<span class="muted small">（還沒選）</span>';
}

/** Close the wizard and forget the picks. */
function closeAddModal() {
  document.getElementById('addModal').style.display = 'none';
  document.getElementById('previewResults').style.display = 'none';
  pickedFolders = [];
  renderPickedFolders();
}

/**
 * Estimate lectures, jobs and quota for the picked folders.
 * @returns {Promise<void>}
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
 * @returns {Promise<void>}
 */
async function loadAddOptions() {
  const box = document.getElementById('addOptions');
  try {
    const data = await (await fetch('/api/generation-options')).json();
    addDefaults = data.defaults;
    const all = { mock_exam_questions: COURSE_FIELD_LABELS.mock_exam_questions, ...OPTION_LABELS };
    box.innerHTML = `<div class="settings-grid">
      ${Object.keys(all).map(key => renderOptionField(key, all[key][0], all[key][1], data.defaults[key], data.choices, undefined, data.defaults)).join('')}
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
 * @returns {Promise<void>}
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
