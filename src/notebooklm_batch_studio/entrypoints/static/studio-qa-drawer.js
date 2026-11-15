/* Gemini Notebook 學習工作室 — Floating exploratory Q&A drawer (⌘J), multi-turn conversation,
   one-click summary synthesis, citation jumping, and quiz explanation collector. */

const qaState = {
  conversationId: null,
  messages: [],
  busy: false,
  loadedCode: null,
};

/**
 * Persist the current course's Q&A drawer history to localStorage.
 * @returns {void}
 */
function saveQaHistory() {
  const code = typeof currentStudyCourse !== 'undefined' && currentStudyCourse?.code;
  if (!code) return;
  try {
    localStorage.setItem(`nb_qa_chat_${code}`, JSON.stringify({
      conversationId: qaState.conversationId,
      messages: qaState.messages.slice(-40),
    }));
  } catch {}
}

/**
 * Restore the current course's Q&A drawer history from localStorage when switching courses or reloading.
 * @returns {void}
 */
function loadQaHistory() {
  const code = typeof currentStudyCourse !== 'undefined' && currentStudyCourse?.code;
  if (!code || qaState.loadedCode === code) return;
  qaState.loadedCode = code;
  try {
    const raw = localStorage.getItem(`nb_qa_chat_${code}`);
    const saved = raw ? JSON.parse(raw) : null;
    qaState.conversationId = saved?.conversationId || null;
    qaState.messages = Array.isArray(saved?.messages) ? saved.messages : [];
  } catch {
    qaState.conversationId = null;
    qaState.messages = [];
  }
  renderQaMessages();
}

/**
 * Toggle the floating Q&A drawer open or closed and sync lecture scope options.
 * @param {boolean|null} forceOpen Optional explicit open state
 * @returns {void}
 */
function toggleQaDrawer(forceOpen = null) {
  const drawer = document.getElementById('qaDrawer');
  if (!drawer) return;
  const shouldOpen = forceOpen === null ? !drawer.classList.contains('open') : Boolean(forceOpen);
  drawer.classList.toggle('open', shouldOpen);
  drawer.setAttribute('aria-hidden', shouldOpen ? 'false' : 'true');
  if (shouldOpen) {
    loadQaHistory();
    syncQaScopeOptions();
    document.getElementById('qaQuestionInput')?.focus();
  }
}

/**
 * Populate the lecture scope dropdown inside the Q&A drawer from the active course.
 * @returns {void}
 */
function syncQaScopeOptions() {
  const select = document.getElementById('qaScopeSelect');
  if (!select) return;
  const lectures = (typeof currentStudyCourse !== 'undefined' && currentStudyCourse && currentStudyCourse.lectures) || [];
  const opts = ['<option value="all">全部講義</option>'];
  lectures.forEach(lec => {
    const no = lec.no ?? lec.lecture_no;
    const title = lec.topic ?? lec.title ?? '';
    if (no === undefined || no === null) return;
    const label = `L${String(no).padStart(2, '0')} ${title}`.trim();
    opts.push(`<option value="${no}">${escHtml(label)}</option>`);
  });
  select.innerHTML = opts.join('');
  if (typeof activeStudyLectureNo !== 'undefined' && activeStudyLectureNo !== null) {
    select.value = String(activeStudyLectureNo);
  }
  syncQaPicker(select);
}

/**
 * Sync or build the custom pill dropdown (.qa-pick) for a QA drawer <select>.
 * @param {HTMLSelectElement|null} select Native select element to mirror
 * @returns {void}
 */
function syncQaPicker(select) {
  if (!select) return;
  let wrap = select.closest('.qa-pick');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.className = 'qa-pick';
    select.parentNode.insertBefore(wrap, select);
    wrap.appendChild(select);
    select.classList.add('sr-only');
    select.tabIndex = -1;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'qa-pick-btn';
    btn.innerHTML = '<span></span><i class="icon-chevron-down"></i>';
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const wasOpen = wrap.classList.contains('open');
      document.querySelectorAll('#qaDrawer .qa-pick.open').forEach(p => p.classList.remove('open'));
      if (!wasOpen) wrap.classList.add('open');
    });
    const pop = document.createElement('div');
    pop.className = 'qa-pop';
    pop.setAttribute('role', 'listbox');
    wrap.append(btn, pop);
  }
  const activeOpt = select.options[select.selectedIndex] || select.options[0];
  wrap.querySelector('.qa-pick-btn span').textContent = activeOpt ? activeOpt.textContent : '';
  const pop = wrap.querySelector('.qa-pop');
  pop.innerHTML = Array.from(select.options).map(o => {
    const on = o.value === select.value ? ' on' : '';
    return `<button type="button" class="qa-pop-item${on}" role="option" aria-selected="${o.value === select.value}" data-val="${escHtml(o.value)}"><span>${escHtml(o.textContent)}</span>${on ? '<i class="icon-circle-check" style="font-size:14px;flex:none"></i>' : ''}</button>`;
  }).join('');
  pop.querySelectorAll('.qa-pop-item').forEach(item => item.addEventListener('click', e => {
    e.stopPropagation();
    select.value = item.dataset.val;
    wrap.classList.remove('open');
    syncQaPicker(select);
    select.dispatchEvent(new Event('change', { bubbles: true }));
  }));
}

document.querySelectorAll('#qaDrawer select.qa-select').forEach(syncQaPicker);
document.addEventListener('click', e => {
  if (!(e.target instanceof Element && e.target.closest('.qa-pick'))) {
    document.querySelectorAll('#qaDrawer .qa-pick.open').forEach(p => p.classList.remove('open'));
  }
});

/**
 * Resolve the currently selected lecture number in the Q&A drawer, or null for all.
 * @returns {number|null} Selected lecture number or null
 */
function selectedQaLectureNo() {
  const val = document.getElementById('qaScopeSelect')?.value;
  if (!val || val === 'all') return null;
  const num = Number(val);
  return Number.isFinite(num) ? num : null;
}

/**
 * Reset the drawer conversation to start a fresh topic.
 * @returns {void}
 */
function resetQaConversation() {
  qaState.conversationId = null;
  qaState.messages = [];
  saveQaHistory();
  renderQaMessages();
  showToast('已開啟新話題', 'info', 1800);
}

/**
 * Post a single Q&A question to the backend and return parsed response JSON.
 * @param {string} question User question text
 * @returns {Promise<object>} Backend answer payload
 */
async function postQaAsk(question) {
  const res = await fetch(`/api/courses/${currentStudyCourse.code}/qa/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      lecture_no: selectedQaLectureNo(),
      conversation_id: qaState.conversationId,
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || res.statusText);
  return data;
}

/**
 * Send the user's question in the Q&A drawer to the backend.
 * @returns {Promise<void>} Resolves when the answer is rendered
 */
async function sendQaQuestion() {
  if (qaState.busy || typeof currentStudyCourse === 'undefined' || !currentStudyCourse) return;
  const input = document.getElementById('qaQuestionInput');
  const sendBtn = document.getElementById('qaSendBtn');
  const question = (input?.value || '').trim();
  if (!question) return;
  qaState.busy = true;
  if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '等待中…'; }
  qaState.messages.push({ role: 'user', text: question, references: [] });
  saveQaHistory();
  input.value = '';
  renderQaMessages();
  try {
    const data = await postQaAsk(question);
    qaState.conversationId = data.conversation_id || qaState.conversationId;
    qaState.messages.push({
      role: 'ai', question, text: data.answer || '', references: data.references || [],
    });
    if (typeof window.registerQaCitations === 'function') window.registerQaCitations(data.references || []);
  } catch (err) {
    qaState.messages.push({ role: 'ai', text: `⚠️ 提問失敗：${err.message}`, references: [], error: true });
  } finally {
    qaState.busy = false;
    if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = '發問'; }
    saveQaHistory();
    renderQaMessages();
  }
}

/**
 * Render all chat turns inside the Q&A drawer.
 * @returns {void}
 */
function renderQaMessages() {
  const box = document.getElementById('qaDrawerMsgs');
  if (!box) return;
  if (!qaState.messages.length && !qaState.busy) {
    box.innerHTML = '<div class="empty-state small">針對本講或整門課向 Gemini Notebook 發問，多輪追問後可一鍵整理成結構化筆記。</div>';
    return;
  }
  const typingHtml = qaState.busy
    ? '<div class="qa-msg ai qa-typing" aria-live="polite"><span class="qa-typing-dots" aria-hidden="true"><i></i><i></i><i></i></span><span>已連線，正在等待 Gemini Notebook 回應…</span></div>'
    : '';
  box.innerHTML = qaState.messages.map((m, idx) => renderOneQaMessage(m, idx)).join('') + typingHtml;
  box.scrollTop = box.scrollHeight;
}

/**
 * Render a single Q&A message bubble with citation chips and save button.
 * @param {object} msg Message record
 * @param {number} idx Index in qaState.messages
 * @returns {string} HTML string
 */
function renderOneQaMessage(msg, idx) {
  if (msg.role === 'user') return `<div class="qa-msg user">${escHtml(msg.text)}</div>`;
  const cites = (msg.references || []).map((r, rIdx) => (
    `<button type="button" class="qa-cite" onclick="jumpToQaCitation(${idx}, ${rIdx})" title="${escHtml(r.cited_text || '')}">[${r.citation_number || rIdx + 1}] 引用片段</button>`
  )).join('');
  const saveBtn = msg.error ? '' : `<button type="button" class="btn btn-soft btn-sm" onclick="saveSingleQaMessage(${idx})">💾 存為筆記</button>`;
  return `<div class="qa-msg ai"><div>${escHtml(msg.text).replace(/\n/g, '<br>')}</div>${cites ? `<div class="qa-cites">${cites}</div>` : ''}${saveBtn ? `<div class="qa-msg-actions">${saveBtn}</div>` : ''}</div>`;
}

/**
 * Show cited text or jump the PDF reader when clicking a citation chip.
 * @param {number} msgIdx Message index
 * @param {number} refIdx Reference index
 * @returns {void}
 */
function jumpToQaCitation(msgIdx, refIdx) {
  const msg = qaState.messages[msgIdx];
  const ref = msg?.references?.[refIdx];
  if (!ref) return;
  if (typeof window.highlightQaCitationInPdf === 'function' && ref.cited_text) {
    window.highlightQaCitationInPdf(ref.cited_text);
    return;
  }
  const pageMatch = String(ref.cited_text || '').match(/(?:p\.?|page|第)\s*(\d+)/i);
  if (pageMatch && typeof window.jumpToPdfPage === 'function') {
    window.jumpToPdfPage(Number(pageMatch[1]));
    return;
  }
  showToast(ref.cited_text ? `引用內容：${ref.cited_text.slice(0, 140)}` : '已定位引用來源', 'info', 4000);
}

/**
 * Save a single Q&A turn as a structured course note.
 * @param {number} idx Message index in qaState.messages
 * @returns {Promise<void>} Resolves when saved
 */
async function saveSingleQaMessage(idx) {
  const msg = qaState.messages[idx];
  if (!msg || typeof currentStudyCourse === 'undefined' || !currentStudyCourse) return;
  const title = (msg.question || '探索提問筆記').slice(0, 40);
  const memo = (document.getElementById('qaQuickMemoInput')?.value || '').trim();
  const body = msg.question ? `## 問題\n${msg.question}\n\n## 解答\n${msg.text}` : msg.text;
  await persistQaNote({
    title,
    content_markdown: body,
    lecture_no: selectedQaLectureNo(),
    tags: [],
    source_scene: 'chat_drawer',
    personal_memo: memo,
  });
}

/**
 * Synthesize the current multi-turn Q&A conversation into a structured note draft and save it.
 * @returns {Promise<void>} Resolves when summary is generated and saved
 */
async function summarizeQaConversation() {
  if (!qaState.conversationId || typeof currentStudyCourse === 'undefined' || !currentStudyCourse) {
    showToast('請先至少提問一輪再整理精華', 'info', 2200);
    return;
  }
  const btn = document.getElementById('qaSummarizeBtn');
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/qa/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: qaState.conversationId,
        lecture_no: selectedQaLectureNo(),
        scene: 'chat_drawer',
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const memo = (document.getElementById('qaQuickMemoInput')?.value || '').trim();
    await persistQaNote({
      title: data.title || '對話精華筆記',
      content_markdown: data.markdown || '',
      lecture_no: selectedQaLectureNo(),
      tags: data.tags || [],
      source_scene: 'chat_drawer',
      personal_memo: memo,
    });
  } catch (err) {
    showToast(`整理精華失敗：${err.message}`, 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/**
 * Persist a note payload via POST /api/courses/{code}/notes and refresh the notes tab if loaded.
 * @param {object} payload Note creation payload
 * @returns {Promise<object|null>} Saved note object or null on error
 */
async function persistQaNote(payload) {
  if (typeof currentStudyCourse === 'undefined' || !currentStudyCourse) return null;
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    showToast('已收錄至問答筆記庫', 'success', 2400);
    if (typeof loadCourseNotes === 'function') loadCourseNotes();
    return data;
  } catch (err) {
    showToast(`儲存筆記失敗：${err.message}`, 'error');
    return null;
  }
}

/**
 * Collect a quiz or mistake explanation box directly into the QA notes library.
 * @param {HTMLElement} btn The collector button inside `.explain-box`
 * @returns {Promise<void>} Resolves when saved
 */
async function collectExplanationAsNote(btn) {
  const box = btn.closest('.explain-box');
  if (!box) return;
  const card = box.closest('.q-card, #mistakeDetail') || box.parentElement;
  const qTitle = card?.querySelector('.q-title')?.textContent?.trim() || '測驗詳解筆記';
  const clone = box.cloneNode(true);
  clone.querySelector('.explain-head')?.remove();
  const explainText = (clone.innerText || clone.textContent || '').trim();
  const lec = typeof activeStudyLectureNo !== 'undefined' ? activeStudyLectureNo : null;
  await persistQaNote({
    title: qTitle.slice(0, 48),
    content_markdown: `## 題目\n${qTitle}\n\n## 解析\n${explainText}`,
    lecture_no: lec,
    tags: [],
    source_scene: 'quiz_explain',
    personal_memo: '',
  });
}

/**
 * Close the drawer and jump to the full QA notes studio tab.
 * @returns {void}
 */
function expandQaToStudioTab() {
  toggleQaDrawer(false);
  if (typeof showView === 'function') showView('studio');
  if (typeof setChoice === 'function') setChoice('studioPane', 'study', false);
  const pane = document.getElementById('paneStudy');
  if (pane && pane.dataset.layout === 'split' && pane.classList.contains('side-collapsed')) {
    pane.querySelector(':scope > .col-resizer .col-toggle')?.click();
  }
  if (typeof selectTool === 'function') selectTool('qa_notes');
  if (pane && pane.dataset.layout !== 'split') {
    document.getElementById('bench')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

/**
 * Update Gemini Notebook chat goal and response length for the current course.
 * @returns {Promise<void>} Resolves when configured
 */
async function configureQaChatStyle() {
  if (typeof currentStudyCourse === 'undefined' || !currentStudyCourse) return;
  const goal = document.getElementById('qaChatGoalSelect')?.value || 'default';
  const responseLength = document.getElementById('qaChatLenSelect')?.value || 'default';
  const customEl = document.getElementById('qaChatCustomPrompt');
  if (customEl) customEl.style.display = goal === 'custom' ? '' : 'none';
  const customPrompt = goal === 'custom' && customEl ? customEl.value.trim() : null;
  if (goal === 'custom' && !customPrompt) { customEl?.focus(); return; }
  try {
    const res = await fetch(`/api/courses/${currentStudyCourse.code}/qa/configure`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, response_length: responseLength, custom_prompt: customPrompt }),
    });
    if (!res.ok) throw new Error(res.statusText);
    showToast('已套用對話角色與篇幅設定', 'success', 1800);
  } catch (err) {
    showToast(`套用設定失敗：${err.message}`, 'error');
  }
}

document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'j') {
    e.preventDefault();
    toggleQaDrawer();
  }
});

document.getElementById('qaQuestionInput')?.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendQaQuestion();
  }
});
