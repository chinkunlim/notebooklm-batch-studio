/**
 * Learning-site viewer (SPEC-021, ADR-016): frames a Gemini-generated site from the sandboxed
 * `/api/artifacts/{code}/site/...` route and keeps its progress.
 * The site runs with an opaque origin, so it has no localStorage of its own: the server injects an
 * adapter that reads saved progress from the frame URL's `#nbs-site=` fragment (never sent to the
 * server) and posts every change here; this page stores it under `nbsSite:<code>/<path>`.
 * Uses escHtml (studio-escape.js).
 */

const SITE_STORE_PREFIX = 'nbsSite:';
const SITE_MAX_BYTES = 2000000;

/**
 * Read a site's saved progress (JSON object text).
 * @param {string} key `<code>/<path>` of the site
 * @returns {string} Saved JSON text, or '{}'
 */
function readSiteProgress(key) {
  try { return localStorage.getItem(SITE_STORE_PREFIX + key) || '{}'; } catch (e) { return '{}'; }
}

/**
 * Show a learning site inside the workbench viewer.
 * @param {HTMLElement} container Viewer container
 * @param {string} code Course code
 * @param {string} path Course-relative path of the site's HTML file
 */
function renderLearningSite(container, code, path) {
  const url = `/api/artifacts/${encodeURIComponent(code)}/site/${encodeURI(path)}`;
  container.innerHTML = `<div class="row small muted" style="flex-wrap:wrap;margin-bottom:var(--s3)">
      <a class="reader-pill-btn" href="${escHtml(url)}" target="_blank" rel="noopener">新分頁開啟（作答進度不保存）</a></div>
    <iframe class="report-frame" data-site="1" sandbox="allow-scripts allow-modals allow-downloads" title="學習網頁"></iframe>`;
  const frame = container.querySelector('iframe[data-site]');
  const key = `${code}/${path}`;
  frame.dataset.siteKey = key;
  frame.src = `${url}#nbs-site=${encodeURIComponent(readSiteProgress(key))}`;
}

/**
 * Save progress posted by the framed site; only messages from that frame are accepted.
 * @param {MessageEvent} event Message from a framed site
 */
function onSiteStorageMessage(event) {
  const frame = document.querySelector('iframe[data-site]');
  if (!frame || event.source !== frame.contentWindow) return;
  const data = event.data;
  if (!data || data.type !== 'nbs-site-storage' || !data.items || typeof data.items !== 'object') return;
  if (!Object.values(data.items).every(v => typeof v === 'string')) return;
  const text = JSON.stringify(data.items);
  if (text.length > SITE_MAX_BYTES) return;
  try { localStorage.setItem(SITE_STORE_PREFIX + frame.dataset.siteKey, text); } catch (e) { /* storage unavailable */ }
}

window.addEventListener('message', onSiteStorageMessage);
