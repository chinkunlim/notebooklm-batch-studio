/*nbs-site-storage*/
/**
 * Storage adapter injected inline at the top of every learning site (SPEC-021, ADR-016).
 * The site is served with a CSP `sandbox` (opaque origin), so the browser's localStorage is
 * unavailable. This keeps storage in memory, starts from progress the study workspace put in the
 * URL fragment (`#nbs-site=<json>`, removed at once; Chromium clears `window.name` on the way into
 * an opaque origin), and posts every change to the framing workspace.
 * Not loaded by the app itself; `entrypoints/http/learning_site.py` reads and inlines it.
 */
(function () {
  var saved = {};
  var tag = '#nbs-site=';
  if (location.hash.indexOf(tag) === 0) {
    try { saved = JSON.parse(decodeURIComponent(location.hash.slice(tag.length))) || {}; } catch (e) { saved = {}; }
    try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { /* keep the hash */ }
  }

  /**
   * Build a Storage-like object over a plain object.
   * @param {object} data Key/value strings
   * @param {Function} persist Called after every change
   * @returns {object} Object with the Storage methods and `length`
   */
  function makeStorage(data, persist) {
    var api = {
      getItem: function (k) {
        k = String(k);
        return Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null;
      },
      setItem: function (k, v) { data[String(k)] = String(v); persist(); },
      removeItem: function (k) { delete data[String(k)]; persist(); },
      clear: function () { Object.keys(data).forEach(function (k) { delete data[k]; }); persist(); },
      key: function (i) { var keys = Object.keys(data); return i < keys.length ? keys[i] : null; },
    };
    Object.defineProperty(api, 'length', { get: function () { return Object.keys(data).length; } });
    return api;
  }

  /** Post the saved progress to the study workspace that frames this site. */
  function send() {
    try {
      if (window.parent !== window) window.parent.postMessage({ type: 'nbs-site-storage', items: saved }, '*');
    } catch (e) { /* not framed by the study workspace */ }
  }

  var local = makeStorage(saved, send);
  var session = makeStorage({}, function () {});
  try {
    Object.defineProperty(window, 'localStorage', { configurable: true, get: function () { return local; } });
  } catch (e) { /* keep the browser's own */ }
  try {
    Object.defineProperty(window, 'sessionStorage', { configurable: true, get: function () { return session; } });
  } catch (e) { /* keep the browser's own */ }
})();
