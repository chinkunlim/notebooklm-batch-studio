/* Gemini Notebook 學習工作室 — core UI behaviour shared by every page section.
   Dialogs close with ✖, a click outside or Esc; fetch retries once and shows an "offline" banner
   instead of a bare "Failed to fetch"; quiz choices are reshuffled on every attempt; the title goes home.
   Uses globals from index.html / studio.js: switchMainView, closeDetail, askConfirm, pickedFolders. */

/* ---------- Dialogs ---------- */
/** Close function for each dialog; dialogs not listed are simply hidden. */
const MODAL_CLOSERS = {
  addModal: () => closeAddModalSafely(),
  usageModal: () => closeUsageModal(),
  namingModal: () => closeNamingModal(),
  promptModal: () => closePromptModal(),
};

/**
 * Close one dialog using its own close function when it has one.
 * @param {HTMLElement} overlay The `.modal-overlay` element
 */
function closeModal(overlay) {
  const closer = MODAL_CLOSERS[overlay.id];
  if (closer) closer(); else overlay.style.display = 'none';
}

/**
 * Close the add-course wizard, asking first when folders were already picked.
 * @returns {Promise<void>}
 */
async function closeAddModalSafely() {
  const picked = typeof pickedFolders !== 'undefined' && pickedFolders.length > 0;
  if (picked && !(await askConfirm('已選的資料夾和設定還沒加入，確定要關閉嗎？', { okLabel: '關閉' }))) return;
  closeAddModal();
}

/**
 * Return the dialogs currently shown, the one on top last.
 * @returns {Array<HTMLElement>} Visible overlays
 */
function visibleOverlays() {
  return [...document.querySelectorAll('.modal-overlay, #confirmOverlay')]
    .filter(el => getComputedStyle(el).display !== 'none');
}

/**
 * Give every dialog a ✖ button and close it on a click outside the box.
 * A drag that starts inside the box (selecting text) does not count as an outside click.
 */
function initModals() {
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    const box = overlay.querySelector('.modal');
    if (box && !box.querySelector(':scope > .modal-x')) {
      const x = document.createElement('button');
      x.className = 'modal-x';
      x.type = 'button';
      x.setAttribute('aria-label', '關閉');
      x.textContent = '✖';
      x.onclick = () => closeModal(overlay);
      box.prepend(x);
    }
    let downOnOverlay = false;
    overlay.addEventListener('mousedown', e => { downOnOverlay = e.target === overlay; });
    overlay.addEventListener('click', e => {
      if (e.target === overlay && downOnOverlay) closeModal(overlay);
      downOnOverlay = false;
    });
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    const top = visibleOverlays().pop();
    if (!top) return;
    if (top.id === 'confirmOverlay') document.getElementById('confirmCancel')?.click();
    else closeModal(top);
  });
}

/* ---------- Network: one retry, then a clear banner ---------- */
const nativeFetch = window.fetch.bind(window);

/**
 * Show or hide the banner that says the local server is not answering.
 * @param {boolean} show True to show it
 */
function setOfflineBanner(show) {
  let bar = document.getElementById('offlineBanner');
  if (!bar && show) {
    bar = document.createElement('div');
    bar.id = 'offlineBanner';
    bar.setAttribute('role', 'alert');
    bar.innerHTML = '⚠️ 伺服器沒有回應，請確認學習工作室已啟動（雙擊「Gemini Notebook 學習工作室」）。'
      + ' <button type="button" onclick="location.reload()">重新整理</button>';
    document.body.appendChild(bar);
  }
  if (bar) bar.style.display = show ? 'flex' : 'none';
}

/**
 * fetch() with one automatic retry for reads, and a readable message when the server is down.
 * Writes (POST/PUT/DELETE) are never retried, so nothing is sent twice.
 * @param {RequestInfo} input URL or request
 * @param {RequestInit} init Fetch options
 * @returns {Promise<Response>} The response
 */
async function apiFetch(input, init = {}) {
  const method = String(init.method || 'GET').toUpperCase();
  try {
    const res = await nativeFetch(input, init);
    setOfflineBanner(false);
    return res;
  } catch (err) {
    if (err && err.name === 'AbortError') throw err;
    if (method === 'GET') {
      await new Promise(r => setTimeout(r, 800));
      try {
        const res = await nativeFetch(input, init);
        setOfflineBanner(false);
        return res;
      } catch (retryErr) {
        err = retryErr;
      }
    }
    setOfflineBanner(true);
    throw new Error('伺服器沒有回應');
  }
}
window.fetch = apiFetch;

/* ---------- Quiz: new choice order on every attempt ---------- */
/** Options whose meaning depends on their position ("以上皆是", "A 和 B") keep the original order. */
const POSITIONAL_OPTION = /以上|上述|皆是|皆非|都對|都錯|all of the above|none of the above|\b[A-D]\s*(和|與|及|、|and)/i;

/**
 * Return a copy of a question with its choices in a new random order and the answer index moved with them.
 * The order is kept when any option refers to other options by position.
 * @param {{choices: Array, answer_index: number}} q Question
 * @param {function(): number} rand Random number source in [0, 1)
 * @returns {object} The shuffled copy
 */
function shuffleQuestion(q, rand = Math.random) {
  const choices = q.choices || [];
  const text = c => (c && c.text !== undefined ? c.text : String(c));
  if (choices.length < 2 || choices.some(c => POSITIONAL_OPTION.test(text(c)))) return { ...q };
  let order = choices.map((_, i) => i);
  for (let attempt = 0; attempt < 5; attempt++) {
    order = choices.map((_, i) => i);
    for (let i = order.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [order[i], order[j]] = [order[j], order[i]];
    }
    if (order.some((v, i) => v !== i)) break;  // make the change visible
  }
  return { ...q, choices: order.map(i => choices[i]), answer_index: order.indexOf(q.answer_index) };
}

/* ---------- Title goes home ---------- */
/**
 * Go back to the start page: close dialogs, show the course list and scroll to the top.
 */
function goHome() {
  visibleOverlays().forEach(el => { el.style.display = 'none'; });
  switchMainView('admin');
  if (typeof closeDetail === 'function') closeDetail();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.addEventListener('DOMContentLoaded', initModals);
