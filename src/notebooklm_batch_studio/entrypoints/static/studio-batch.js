/* Gemini Notebook 學習工作室 — 批次排程 page: login / queue / quota status, the course list, one course's
   jobs grouped by lecture (prompt, settings, download, regenerate) and the 進行中 column.
   Uses globals from studio-app.js (escHtml, pad2, lectureName, currentCoursesList, renderCourseDirectory,
   initStudyPortal) and studio-settings.js (loadCourseOptions, loadArtifactSelection). */

/* ================= 批次排程 (admin) ================= */

let lastQueueDigest = null;

/**
 * Refresh course summaries and active views whenever queue progress changes (ISSUE-036).
 * @param {string} digest Compact queue state summary
 * @returns {Promise<void>}
 */
async function syncLiveCourseProgress(digest) {
  const changed = lastQueueDigest !== null && lastQueueDigest !== digest;
  lastQueueDigest = digest;
  if (window.StudioStore) window.StudioStore.patch({ queueDigest: digest });
  if (!changed) return;
  if (window.StudioBus) window.StudioBus.emit('queue:changed', digest);
  await fetchCourses();
  if (activeCourseCode && document.getElementById('courseDetailSection').style.display !== 'none') {
    await viewCourseDetail(activeCourseCode, true);
  }
  if (currentStudyCourse && typeof loadStudyCourseData === 'function') {
    await loadStudyCourseData(currentStudyCourse.code, true);
  }
}

/**
 * Read login, queue and course counts; update the top bar and the queue buttons.
 * @returns {Promise<void>}
 */
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    const auth = document.getElementById('authBadge');
    const ok = data.auth && data.auth.authenticated;
    auth.dataset.state = ok ? 'ok' : 'bad';
    auth.innerHTML = `<i class="dot"></i>${ok ? '已連線' : '未登入 Gemini Notebook'}`;
    const queue = document.getElementById('queueBadge');
    const counts = data.queue_counts || {};
    if (data.queue_running) {
      queue.textContent = `佇列 ${counts.running || 0} 項生成中、${counts.pending || 0} 項等待`;
      setQueueButtonsVisible(false, true, false);
    } else if (counts.pending > 0 || counts.quota_wait > 0 || counts.failed > 0) {
      const waitN = (counts.pending || 0) + (counts.quota_wait || 0) + (counts.failed || 0);
      queue.textContent = `佇列已暫停（${waitN} 項待處理${counts.failed ? `・含 ${counts.failed} 項失敗` : ''}）`;
      setQueueButtonsVisible(false, false, true);
    } else {
      queue.textContent = `佇列閒置（已完成 ${counts.done || 0} 項）`;
      setQueueButtonsVisible(true, false, false);
    }
    const digest = `${!!data.queue_running}:${counts.done || 0}:${counts.running || 0}:${counts.pending || 0}:${counts.quota_wait || 0}:${counts.failed || 0}`;
    await syncLiveCourseProgress(digest);
  } catch (e) {
    console.error('Status fetch failed:', e);
  }
}

/**
 * Read the Gemini Notebook generation quota; update the top bar and the ring on the batch page.
 * @returns {Promise<void>}
 */
async function fetchQuota() {
  const badge = document.getElementById('quotaBadge');
  const ring = document.getElementById('quotaRing');
  /**
   * Update the quota ring and its text on the batch page.
   * @param {number|null} pct Remaining percent (null = unknown)
   * @param {string} title Bold line
   * @param {string} text Explanation under it
   */
  const setRing = (pct, title, text) => {
    ring.dataset.p = pct === null ? 0 : Math.max(0, Math.min(100, Math.round(pct)));
    document.getElementById('quotaPct').textContent = pct === null ? '—' : Math.round(pct);
    document.getElementById('quotaTitle').textContent = title;
    document.getElementById('quotaText').textContent = text;
    if (typeof animateRings === 'function') animateRings(ring.parentElement);
  };
  try {
    const res = await fetch('/api/notebooklm/quota');
    const data = await res.json();
    if (!res.ok) {
      badge.textContent = '額度無法讀取';
      badge.title = data.detail || '';
      setRing(null, '生成額度', '無法讀取額度');
      return;
    }
    const names = { five_hour: '5 小時', weekly: '每週' };
    const windows = data.windows || [];
    const parts = windows.map(w => `${names[w.kind] || w.kind} ${Math.round(w.remaining_percent)}%`);
    const low = windows.some(w => w.remaining_percent <= 0);
    badge.dataset.state = low ? 'warn' : '';
    badge.textContent = parts.length ? `額度剩 ${parts.join('・')}` : '額度未提供';
    const resets = windows.map(w => `${names[w.kind] || w.kind}額度 ${new Date(w.resets_at).toLocaleString('zh-TW', { dateStyle: 'short', timeStyle: 'short' })} 重置`).join('；');
    badge.title = resets + (data.source_limit ? `\n每本筆記本來源上限：${data.source_limit}` : '');
    const five = windows.find(w => w.kind === 'five_hour') || windows[0];
    setRing(five ? five.remaining_percent : null, five ? `${names[five.kind] || five.kind}額度剩 ${Math.round(five.remaining_percent)}%` : '生成額度',
      (low ? '用完的工作會等額度重置後自動繼續。' : '額度足夠時會依序生成。') + (resets ? `${resets}。` : ''));
  } catch (e) {
    badge.textContent = '額度無法讀取';
  }
}

/* Queue control, upload retry, prompt refine, and remote sync live in studio-queue.js. */

/**
 * Load the registered courses and draw the list on the batch page (and the 課程目錄).
 * @returns {Promise<void>}
 */
async function fetchCourses() {
  try {
    const res = await fetch('/api/courses');
    const courses = await res.json();
    currentCoursesList = courses;
    const container = document.getElementById('courseContainer');
    if (!courses || courses.length === 0) {
      container.innerHTML = '<li class="empty-state">還沒有課程。按右上角「加入課程」，點選放講義 PDF 的資料夾。</li>';
      renderCourseDirectory(); renderCoursePicker();
      return;
    }
    // Field names follow GET /api/courses (counts / total_jobs / lecture_count). Refs: ISSUE-020
    container.innerHTML = courses.map(c => {
      const stats = c.counts || {};
      const total = (c.total_jobs || 0) - (stats.skipped || 0);
      const done = stats.done || 0;
      const pct = total > 0 ? Math.round((done / total) * 100) : 0;
      const hasNb = !!c.notebook_id;
      const extra = [
        c.paused ? '暫停中' : '',
        !hasNb ? '待建立筆記本' : '',
        stats.running ? `${stats.running} 項生成中` : '',
        stats.pending ? `${stats.pending} 項排隊` : '',
        stats.quota_wait ? `${stats.quota_wait} 項等額度` : '',
        stats.needs_review ? `${stats.needs_review} 項需審查` : '',
        stats.failed ? `${stats.failed} 項失敗` : '',
      ].filter(Boolean).join('・');
      return `<li><button class="${activeCourseCode === c.code ? 'on' : ''}" data-code="${escHtml(c.code)}" onclick="viewCourseDetail(${jsAttr(c.code)})">
          <span class="cr-name">${escHtml(c.name)}（${escHtml(c.code)}）</span><span class="cr-meta">${done} / ${total}　${pct}%</span>
          <span class="cr-meta" style="grid-column:1/-1">${c.lecture_count} 份 PDF${extra ? '・' + extra : ''}</span>
          <span class="meter"><span style="width:${pct}%"></span></span></button>
        ${!hasNb ? `<button class="btn btn-soft btn-sm" style="margin:4px 12px 8px" onclick="setupCourse(${jsAttr(c.code)}, event)">建立筆記本並上傳</button>` : ''}</li>`;
    }).join('');
    renderCourseDirectory(); renderCoursePicker();
  } catch (e) {
    console.error('Fetch courses failed:', e);
  }
}

/** Status names and badge styles for jobs. */
const STATUS_LABELS = {
  done: { text: '完成', cls: 'badge-success' },
  pending: { text: '排隊中', cls: 'badge-neutral' },
  running: { text: '生成中', cls: 'badge-warning' },
  quota_wait: { text: '等待額度', cls: 'badge-warning' },
  needs_review: { text: '需審查', cls: 'badge-warning' },
  failed: { text: '失敗', cls: 'badge-danger' },
};

/**
 * When a job waiting for quota will continue.
 * @param {string} iso Time the quota resets
 * @returns {string} Readable text
 */
function formatResume(iso) {
  const t = new Date(iso);
  const mins = Math.max(0, Math.round((t - new Date()) / 60000));
  const hhmm = t.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
  return mins > 0 ? `預計 ${hhmm} 自動繼續（約 ${mins} 分鐘後）` : '額度已重置，即將自動繼續';
}

/**
 * Counts per status, plus when paused or waiting jobs continue.
 * @param {Array<object>} jobs Jobs of the course
 * @param {boolean} paused Whether the course is paused
 * @param {string} [code] Course code for bulk failed-job retry button
 * @returns {string} HTML
 */
function renderStatusBar(jobs, paused, code) {
  const activeJobs = jobs.filter(j => j.status !== 'skipped');
  const counts = {};
  activeJobs.forEach(j => { counts[j.status] = (counts[j.status] || 0) + 1; });
  const order = ['done', 'running', 'pending', 'quota_wait', 'needs_review', 'failed'];
  const chips = order.filter(k => counts[k]).map(k => `<span class="badge ${STATUS_LABELS[k].cls}">${STATUS_LABELS[k].text} ${counts[k]}</span>`).join('');
  const attnCount = (counts.failed || 0) + (counts.needs_review || 0);
  const retryAllBtn = attnCount && code
    ? `<button class="btn btn-soft btn-sm" onclick="retryFailedJobs(${jsAttr(code)})">重試失敗／需審查項目（${attnCount}）</button>` : '';
  const waits = activeJobs.filter(j => j.status === 'quota_wait' && j.cooldown_until).map(j => j.cooldown_until).sort();
  const notes = [];
  if (paused) notes.push('這門課暫停中，按上方「開始生成」才會繼續。');
  else if (waits.length) notes.push(`額度用完的工作會等額度重置，${formatResume(waits[0])}。網頁服務開著就會自己接著跑。`);
  if (counts.failed) notes.push('失敗的工作在冷卻後會由背景自動重試，也可按「重試」立即重新執行。');
  const noteHtml = notes.length ? `<div class="status-note">${notes.join(' ')}</div>` : '';
  return `<div class="status-chips"><strong class="small">共 ${activeJobs.length} 項</strong>${chips}${retryAllBtn}</div>${noteHtml}`;
}

/**
 * Semantic colour token for an artifact type (the same hue as its tile).
 * @param {string} type Artifact type
 * @returns {string} CSS custom property name
 */
function hueFor(type) {
  const t = String(type);
  if (t.includes('audio')) return '--h-audio';
  if (t.includes('video')) return '--h-video';
  if (t.includes('quiz') || t.includes('mock_exam')) return '--h-quiz';
  if (t.includes('flashcards')) return '--h-flash';
  if (t.includes('mind_map')) return '--h-mindmap';
  if (t.includes('infographic')) return '--h-infographic';
  if (t.includes('slide')) return '--h-slides';
  if (t.includes('data_table')) return '--h-table';
  return '--h-report';
}

/**
 * Show the running and waiting jobs of a course in the 進行中 column.
 * @param {Array<object>} jobs Jobs of the course
 * @param {string} code Course code
 */
function renderActiveJobs(jobs, code) {
  const rank = { running: 0, pending: 1, quota_wait: 2, failed: 3, needs_review: 4 };
  const list = jobs.filter(j => j.status in rank).sort((a, b) => rank[a.status] - rank[b.status]).slice(0, 8);
  const width = { running: 50, pending: 4, quota_wait: 4, failed: 100, needs_review: 100 };
  document.getElementById('activeJobs').innerHTML = list.length ? list.map(j => {
    const scope = j.lecture_no === null ? '整門課' : lectureName(j.lecture_no);
    const st = STATUS_LABELS[j.status] || { text: j.status };
    const hue = j.status === 'failed' ? '--danger' : hueFor(j.artifact_type);
    const retryBtn = (j.status === 'failed' || j.status === 'needs_review')
      ? `<button class="btn btn-ghost btn-sm" onclick="retryJob(${jsAttr(j.id)}, ${jsAttr(code)})">重試</button>` : '';
    return `<li style="--hue:var(${hue})"><div class="job-top"><span>${scope}　${escHtml(j.label || j.artifact_type)}</span><span>${st.text} ${retryBtn}</span></div><div class="bar hue"><i style="width:${width[j.status]}%"></i></div></li>`;
  }).join('') : `<li class="small muted">${escHtml(code)} 目前沒有進行中的工作。</li>`;
}

/**
 * One job row: name, version, status, prompt / settings buttons, download and regenerate.
 * @param {object} j Job
 * @param {string} code Course code
 * @param {object} versionsBySlot Newest version per "lecture|type"
 * @returns {string} HTML
 */
function jobRowHtml(j, code, versionsBySlot) {
  const st = STATUS_LABELS[j.status] || { text: j.status, cls: '' };
  const scope = j.lecture_no ? `L${pad2(j.lecture_no)}` : '全課程';
  const target = j.rel_path || (j.output_file ? j.output_file.split('/').pop() : null);
  const dlName = target ? target.split('/').pop() : null;
  const dlLink = target ? `<a href="/api/artifacts/${code}/download/${encodeURI(target)}" target="_blank" rel="noopener" class="btn btn-ghost btn-sm">${escHtml(dlName.split('.').pop().toUpperCase())}</a>` : '—';
  const hasOwn = j.style_options ? ' ✱' : '';
  const total = versionsBySlot[`${j.lecture_no}|${j.artifact_type}`] || 1;
  const ver = `<span class="badge ${j.version > 1 ? 'badge-warning' : ''}">v${j.version || 1}</span>` +
    (total > 1 && j.version === total ? `<div class="job-sub">已生成 ${total} 版</div>` : '');
  let statusExtra = '';
  if (j.status === 'quota_wait' && j.cooldown_until) statusExtra = `<div class="job-sub">${formatResume(j.cooldown_until)}</div>`;
  else if ((j.status === 'needs_review' || j.status === 'failed') && j.error_message) statusExtra = `<div class="job-sub">${escHtml(j.error_message.slice(0, 80))}</div>`;
  const lecArg = j.lecture_no === null ? 'null' : j.lecture_no;
  const retryBtn = (j.status === 'failed' || j.status === 'needs_review')
    ? `<button class="btn btn-primary btn-sm" onclick="retryJob(${jsAttr(j.id)}, ${jsAttr(code)})">重試</button>` : '';
  const regenBtn = (j.status === 'done' || j.status === 'needs_review' || j.status === 'failed') && j.version === total
    ? `<button class="btn btn-soft btn-sm" onclick="regenerateArtifact(${jsAttr(code)}, ${lecArg}, ${jsAttr(j.artifact_type)}, { label: ${jsAttr(j.label || j.artifact_type)}, nextVersion: ${total + 1} })">重新生成</button>` : '';
  return `<tr><td><strong>${escHtml(j.label || j.artifact_type)}</strong><div class="job-sub"><code>${j.artifact_type}</code>　${scope}</div></td><td>${ver}</td>
    <td><span class="badge ${st.cls}">${st.text}</span>${statusExtra}</td>
    <td><button class="btn btn-ghost btn-sm" onclick="openPromptEditor(${jsAttr(j.id)}, ${jsAttr(`${scope} - ${j.artifact_type}`)})">Prompt</button><button class="btn btn-ghost btn-sm" onclick="openJobOptions(${jsAttr(j.id)})" title="只調整這一份產出的設定">設定${hasOwn}</button></td>
    <td>${dlLink}</td><td><div style="display:flex;gap:6px;flex-wrap:wrap">${retryBtn}${regenBtn}</div></td></tr>`;
}

/**
 * Every job grouped by lecture (whole course last); groups that need attention or are busy start open.
 * @param {object} data Course from GET /api/courses/{code}
 * @param {string} code Course code
 * @returns {string} HTML
 */
function jobGroupsHtml(data, code) {
  const jobs = data.jobs || [];
  const versionsBySlot = {};
  jobs.forEach(j => {
    const slot = `${j.lecture_no}|${j.artifact_type}`;
    versionsBySlot[slot] = Math.max(versionsBySlot[slot] || 0, j.version || 1);
  });
  const tableHead = '<table><thead><tr><th style="width:30%">產物</th><th>版本</th><th>狀態</th><th>Prompt / 設定</th><th>檔案</th><th></th></tr></thead><tbody>';
  const groups = new Map();
  (data.lectures || []).forEach(l => groups.set(l.no, []));
  groups.set('course', []);
  jobs.filter(j => j.status !== 'skipped').forEach(j => {
    const key = j.lecture_no === null ? 'course' : j.lecture_no;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(j);
  });
  const topicOf = no => ((data.lectures || []).find(l => l.no === no) || {}).topic || '';
  return [...groups.entries()].sort((a, b) => (a[0] === 'course') - (b[0] === 'course') || a[0] - b[0]).map(([key, list]) => {
    const done = list.filter(j => j.status === 'done').length;
    const attention = list.some(j => ['failed', 'needs_review'].includes(j.status));
    const busy = list.some(j => ['running', 'pending', 'quota_wait'].includes(j.status));
    const title = key === 'course' ? '整門課' : `第 ${pad2(key)} 講・${escHtml(topicOf(key))}`;
    const badge = attention ? 'badge-danger' : !list.length ? '' : done === list.length ? 'badge-success' : 'badge-warning';
    const body = list.length ? `${tableHead}${list.map(j => jobRowHtml(j, code, versionsBySlot)).join('')}</tbody></table>` : '<p class="small muted">目前尚未排入此範圍的產出項目。</p>';
    const addBar = typeof addArtifactBarHtml === 'function' ? addArtifactBarHtml(code, key, list) : '';
    return `<details class="job-group" ${attention || busy ? 'open' : ''}>
      <summary><span>${title}</span><span class="badge ${badge}">${done} / ${list.length} 完成${attention ? '・需處理' : ''}</span></summary>
      <div>${body}${addBar}</div></details>`;
  }).join('');
}

/**
 * The course's pause / start button and its advanced tools menu.
 * @param {string} code Course code
 * @param {boolean} paused Whether the course is paused
 * @returns {string} HTML
 */
function courseActionsHtml(code, paused) {
  return (paused
    ? `<span class="badge badge-warning">暫停中</span><button class="btn btn-primary btn-sm" onclick="setCoursePaused(${jsAttr(code)}, false)">開始生成</button>`
    : `<button class="btn btn-soft btn-sm" onclick="setCoursePaused(${jsAttr(code)}, true)">暫停這門課</button>`) +
    `<details class="more-menu"><summary class="btn btn-ghost btn-sm">進階工具</summary><div class="menu">
      <button class="btn btn-ghost" onclick="syncFromNotebookLM(${jsAttr(code)})">從 Gemini Notebook 同步網頁上做的產出</button>
      <button class="btn btn-ghost" onclick="refinePrompts(${jsAttr(code)})">用本機模型潤飾 Prompt</button>
      <button class="btn btn-ghost" onclick="deleteCourse(${jsAttr(code)})" style="color:var(--danger)">刪除課程</button></div></details>`;
}

/**
 * Open a course on the batch page: settings, output selection and every job grouped by lecture.
 * @param {string} code Course code
 * @param {boolean} silent True for the automatic refresh (keeps scroll, open groups and the forms)
 * @returns {Promise<void>}
 */
async function viewCourseDetail(code, silent = false) {
  activeCourseCode = code;
  const content = document.getElementById('detailContent');
  document.getElementById('courseDetailSection').style.display = 'block';
  document.querySelectorAll('#courseContainer button[data-code]').forEach(b => b.classList.toggle('on', b.dataset.code === code));
  if (!silent) {
    content.innerHTML = '<p class="loading-line">載入中…</p>';
    loadCourseOptions(code);
    loadArtifactSelection(code);
    if (typeof loadCourseSources === 'function') loadCourseSources(code);
    if (typeof loadCourseRemoteArtifacts === 'function') loadCourseRemoteArtifacts(code);
  }
  try {
    const res = await fetch(`/api/courses/${code}`);
    const data = await res.json();
    document.getElementById('detailTitle').textContent = `${data.name || code}（${code}）`;
    // Keep the groups the user opened or closed when the page refreshes itself.
    const openState = new Map([...content.querySelectorAll('details.job-group')].map(d => [d.querySelector('summary span').textContent, d.open]));
    content.innerHTML = renderStatusBar(data.jobs || [], data.paused, code) + jobGroupsHtml(data, code);
    if (silent) {
      content.querySelectorAll('details.job-group').forEach(d => {
        const key = d.querySelector('summary span').textContent;
        if (openState.has(key)) d.open = openState.get(key);
      });
      if (typeof loadCourseSources === 'function') loadCourseSources(code);
      if (typeof loadCourseRemoteArtifacts === 'function') loadCourseRemoteArtifacts(code);
    }
    document.getElementById('detailCourseActions').innerHTML = courseActionsHtml(code, data.paused);
    renderActiveJobs(data.jobs || [], code);
  } catch (e) {
    content.innerHTML = `<p style="color:var(--danger)">載入失敗：${escHtml(e.message)}</p>`;
  }
}

/**
 * Pause or start one course.
 * @param {string} code Course code
 * @param {boolean} paused True to pause
 * @returns {Promise<void>}
 */
async function setCoursePaused(code, paused) {
  try {
    const res = await fetch(`/api/courses/${code}/${paused ? 'pause' : 'start'}`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    await viewCourseDetail(code, true);
    await fetchCourses();
  } catch (e) {
    showToast('操作失敗：' + e.message, 'error');
  }
}

/**
 * Forget every browser/server UI preference scoped to a deleted course (ISSUE-034).
 * @param {string} code Deleted course code
 */
function clearCoursePreferences(code) {
  if (typeof forget !== 'function') return;
  forget('place:' + code);
  forget('examNotice:' + code);
  const prefix = `audio:${code}:`;
  if (typeof mem === 'object' && mem) {
    Object.keys(mem).filter(k => k.startsWith(prefix)).forEach(k => forget(k));
  }
  try {
    Object.keys(localStorage)
      .filter(k => k.startsWith('v05.' + prefix))
      .forEach(k => forget(k.slice(4)));
  } catch (e) { /* cache unavailable */ }
  if (prefLoad('course', '') === code || (currentStudyCourse && currentStudyCourse.code === code)) {
    forget('course');
    currentStudyCourse = null;
  }
}

/**
 * Delete a course's local records after confirmation (files move to DATA_DIR/deleted/).
 * @param {string} code Course code
 * @returns {Promise<void>}
 */
async function deleteCourse(code) {
  if (!(await askConfirm(`刪除課程 ${code}？\n\n• 本機的工作紀錄與學習紀錄會刪除\n• 產出檔案移到 DATA_DIR/deleted/（可找回）\n• 講義 PDF 和 Gemini Notebook 上的筆記本不會動`, { okLabel: '刪除', danger: true }))) return;
  try {
    const res = await fetch(`/api/courses/${code}`, { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    clearCoursePreferences(code);
    showToast(`已刪除 ${code}（${data.removed_jobs} 項工作）` + (data.moved_to ? `\n產出已移到：${data.moved_to}` : ''), 'success', 7000);
    closeDetail();
    activeCourseCode = null;
    if (window.StudioStore) window.StudioStore.patch({ activeCourseCode: null });
    await fetchStatus();
    await fetchCourses();
    await initStudyPortal();
  } catch (e) {
    showToast('刪除失敗：' + e.message, 'error');
  }
}

/**
 * Generate a new version of one output (the old one is kept).
 * @param {string} code Course code
 * @param {number|null} lectureNo Lecture number (null = whole course)
 * @param {string} artifactType Artifact type
 * @param {{label: string, nextVersion: number}} opts Display label and next version number
 * @returns {Promise<void>} Resolves when queued
 */
async function regenerateArtifact(code, lectureNo, artifactType, opts) {
  const { label, nextVersion } = opts;
  const scope = lectureNo === null ? '全課程' : `L${pad2(lectureNo)}`;
  if (!(await askConfirm(`重新生成 ${scope}「${label}」為 v${nextVersion}？\n舊版本會保留，這會使用 Gemini Notebook 額度。`, { okLabel: '重新生成' }))) return;
  try {
    const res = await fetch(`/api/courses/${code}/jobs/regenerate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ artifact_type: artifactType, lecture_no: lectureNo }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    await fetchCourses();
    await viewCourseDetail(code, true);
  } catch (e) {
    showToast('重新生成失敗：' + e.message, 'error');
  }
}
