/**
 * @file studio-hl-colors.js
 * @description User-customizable PDF highlight colors (設計與自訂 → 講義螢光筆顏色).
 */

const HL_COLOR_DEFAULTS = {
  i3: '#e8b83c',
  i2: '#2e6f5b',
  i1: '#6366f1',
  i4: '#e11d48',
  i5: '#0284c7',
};

/**
 * Load saved PDF highlight colors merged with defaults.
 * @returns {Record<string, string>} Map of highlight level keys (i1..i5) to hex colors
 */
function loadHighlightColors() {
  try {
    const raw = typeof load === 'function' ? load('hlColors', '') : localStorage.getItem('v05.hlColors');
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === 'object' ? { ...HL_COLOR_DEFAULTS, ...parsed } : { ...HL_COLOR_DEFAULTS };
  } catch (e) {
    return { ...HL_COLOR_DEFAULTS };
  }
}

/**
 * Apply saved PDF highlight colors to CSS variables and sync the settings inputs.
 * @returns {void}
 */
function applyHighlightColors() {
  const colors = loadHighlightColors();
  const rootEl = document.documentElement;
  Object.entries(colors).forEach(([k, hex]) => {
    rootEl.style.setProperty(`--hl-${k}`, hex);
    const input = document.getElementById(`hlColor-${k}`);
    if (input) input.value = hex;
  });
}

/**
 * Update one PDF highlight color, persist it in preferences, and apply immediately.
 * @param {string} key Highlight key ('i1' | 'i2' | 'i3' | 'i4' | 'i5')
 * @param {string} hex Hex color string
 * @returns {void}
 */
function setHighlightColor(key, hex) {
  const colors = { ...loadHighlightColors(), [key]: hex };
  if (typeof save === 'function') save('hlColors', JSON.stringify(colors));
  else try { localStorage.setItem('v05.hlColors', JSON.stringify(colors)); } catch (e) { /* ignore */ }
  applyHighlightColors();
}

/**
 * Reset all five PDF highlight colors back to defaults.
 * @returns {void}
 */
function resetHighlightColors() {
  if (typeof save === 'function') save('hlColors', JSON.stringify(HL_COLOR_DEFAULTS));
  else try { localStorage.removeItem('v05.hlColors'); } catch (e) { /* ignore */ }
  applyHighlightColors();
  if (typeof notify === 'function') notify('已恢復預設螢光筆顏色');
}

document.querySelectorAll('#hlColorsCard input[data-hl-key]').forEach(inp => {
  inp.addEventListener('input', e => setHighlightColor(e.target.dataset.hlKey, e.target.value));
});
document.getElementById('btnResetHlColors')?.addEventListener('click', resetHighlightColors);
applyHighlightColors();
