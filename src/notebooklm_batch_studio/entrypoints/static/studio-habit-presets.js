/**
 * @file studio-habit-presets.js
 * @description Starter study-habit presets (for new learners) and multi-select tool/AI preferences.
 */

const HABIT_STARTERS = {
  starter: {
    label: '新手引導（預設）',
    focus: 25,
    quizAdvance: 'manual',
    pace: 'relax',
    speed: '1',
    layout: 'stage',
    style: 'flow',
    mmPreset: 'forest-classic',
    aiPrefs: [],
    hiddenTools: [],
  },
  commute: {
    label: '通勤聽讀型',
    focus: 15,
    quizAdvance: 'manual',
    pace: 'relax',
    speed: '1.25',
    layout: 'stage',
    style: 'flow',
    mmPreset: 'forest-classic',
    aiPrefs: ['bullets'],
    hiddenTools: ['video', 'slides', 'table'],
  },
  sprint: {
    label: '考前刷題衝刺',
    focus: 45,
    quizAdvance: 'auto',
    pace: 'sprint',
    speed: '1.25',
    layout: 'split',
    style: 'practice',
    mmPreset: 'exam-mono',
    aiPrefs: ['bullets', 'exam'],
    hiddenTools: ['video', 'infographic', 'slides', 'table'],
  },
  deep: {
    label: '深度精讀筆記',
    focus: 50,
    quizAdvance: 'manual',
    pace: 'relax',
    speed: '1',
    layout: 'split',
    style: 'editorial',
    mmPreset: 'warm-notes',
    aiPrefs: ['bullets', 'examples', 'web_search'],
    hiddenTools: [],
  },
};

const AI_STYLE_OPTIONS = [
  { id: 'bullets', label: '條列重點整理' },
  { id: 'examples', label: '附白話生活舉例' },
  { id: 'exam', label: '標註常見考點' },
  { id: 'web_search', label: '預設開啟網路補充搜尋' },
];

/**
 * Load multi-select preferences (hidden workbench tools and AI answer style flags).
 * @returns {{hiddenTools: string[], aiPrefs: string[]}} Stored multi-select preferences
 */
function loadMultiPrefs() {
  try {
    const raw = typeof load === 'function' ? load('multiPrefs', '') : localStorage.getItem('v05.multiPrefs');
    const parsed = raw ? JSON.parse(raw) : null;
    return {
      hiddenTools: Array.isArray(parsed?.hiddenTools) ? parsed.hiddenTools : [],
      aiPrefs: Array.isArray(parsed?.aiPrefs) ? parsed.aiPrefs : [],
    };
  } catch (e) {
    return { hiddenTools: [], aiPrefs: [] };
  }
}

/**
 * Save multi-select preferences and immediately apply them to the UI.
 * @param {{hiddenTools: string[], aiPrefs: string[]}} prefs Multi-select preferences
 */
function saveMultiPrefs(prefs) {
  if (typeof save === 'function') save('multiPrefs', JSON.stringify(prefs));
  else try { localStorage.setItem('v05.multiPrefs', JSON.stringify(prefs)); } catch (e) { /* ignore */ }
  applyMultiPrefs();
}

/**
 * Toggle one workbench tool's visibility or one AI answer style option.
 * @param {'tools' | 'ai'} group Preference group
 * @param {string} id Option identifier
 * @param {boolean} checked Checkbox state
 */
function toggleMultiPref(group, id, checked) {
  const prefs = loadMultiPrefs();
  if (group === 'tools') {
    const set = new Set(prefs.hiddenTools);
    if (checked) set.delete(id); else set.add(id);
    prefs.hiddenTools = [...set];
  } else {
    const set = new Set(prefs.aiPrefs);
    if (checked) set.add(id); else set.delete(id);
    prefs.aiPrefs = [...set];
    if (id === 'web_search') {
      const box = document.getElementById('qaWebSearchToggle');
      if (box) box.checked = checked;
      try { localStorage.setItem('v05.qaWebSearch', checked ? '1' : '0'); } catch (e) { /* ignore */ }
    }
  }
  saveMultiPrefs(prefs);
}

/**
 * Render multi-select checkboxes for workbench tools and AI response preferences, and hide unchecked tools.
 * @returns {void}
 */
function applyMultiPrefs() {
  const prefs = loadMultiPrefs();
  const hiddenSet = new Set(prefs.hiddenTools);
  const aiSet = new Set(prefs.aiPrefs);
  const tools = typeof TOOLS !== 'undefined' ? TOOLS.filter(t => t.id !== 'audio') : [];
  const toolBox = document.getElementById('benchToolChecks');
  if (toolBox && tools.length) {
    toolBox.innerHTML = tools.map(t => (
      `<label class="multi-chip"><input type="checkbox" ${hiddenSet.has(t.id) ? '' : 'checked'} onchange="toggleMultiPref('tools',${jsAttr(t.id)},this.checked)"><span>${t.name}</span></label>`
    )).join('');
  }
  const aiBox = document.getElementById('aiStyleChecks');
  if (aiBox) {
    aiBox.innerHTML = AI_STYLE_OPTIONS.map(o => (
      `<label class="multi-chip"><input type="checkbox" ${aiSet.has(o.id) ? 'checked' : ''} onchange="toggleMultiPref('ai',${jsAttr(o.id)},this.checked)"><span>${o.label}</span></label>`
    )).join('');
  }
  document.querySelectorAll('#benchTiles .tile[data-tool]').forEach(el => {
    el.hidden = hiddenSet.has(el.dataset.tool);
  });
}

/**
 * Apply a starter study-habit profile for users who have not established fixed habits yet.
 * @param {string} id Starter id ('starter' | 'commute' | 'sprint' | 'deep')
 */
function applyHabitStarter(id) {
  const s = HABIT_STARTERS[id];
  if (!s) return;
  if (typeof save === 'function') save('habitStarter', id);
  document.querySelectorAll('#habitStarterCards [data-starter]').forEach(btn => {
    btn.classList.toggle('on', btn.dataset.starter === id);
  });
  if (typeof setChoice === 'function') {
    setChoice('quizAdvance', s.quizAdvance);
    setChoice('pace', s.pace);
    setChoice('speed', s.speed);
    setChoice('layout', s.layout);
    setChoice('style', s.style);
  }
  const focusInput = document.querySelector('#habitCard input[data-habit="focus"]');
  if (focusInput) {
    focusInput.value = String(s.focus);
    focusInput.dispatchEvent(new Event('input', { bubbles: true }));
  }
  if (typeof applyMindmapPreset === 'function') applyMindmapPreset(s.mmPreset);
  saveMultiPrefs({ hiddenTools: s.hiddenTools, aiPrefs: s.aiPrefs });
  if (typeof notify === 'function') notify(`已套用「${s.label}」學習情境`);
}

document.querySelectorAll('#habitStarterCards [data-starter]').forEach(btn => {
  btn.addEventListener('click', () => applyHabitStarter(btn.dataset.starter));
});
applyMultiPrefs();
