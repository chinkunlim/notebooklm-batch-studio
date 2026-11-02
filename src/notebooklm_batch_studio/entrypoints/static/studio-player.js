/* Gemini Notebook 學習工作室 — the turntable player: plays the lecture's real audio overview, mirrors it in the
   Dock mini player, draws the four visuals (vinyl, sine, ring, LED) on every record size, and runs the
   animation loop only while audio plays. Loaded after studio-shell.js (uses $, setChoice, updateMini, go). */

/* ---------- Player: the turntable plays the lecture's real audio overview ---------- */
const audio = $('#portalAudio');
const player = { playing: false, t: 0, dur: 0, speed: 1, last: 0, src: '', track: null };
const ARC = 381.4; // 270° of r=81
const fmt = s => (Number.isFinite(s) ? `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '00:00');

/** Render the time-dependent parts of the player (arc, bead, clocks) here and in the mini player. */
function renderPlayer() {
  const p = player.dur ? Math.min(1, player.t / player.dur) : 0;
  $('#arcFg').style.strokeDashoffset = ARC * (1 - p);
  const a = (135 + p * 270) * Math.PI / 180;
  const bead = $('#bead');
  bead.style.left = (92 + 81 * Math.cos(a)) + 'px';
  bead.style.top = (92 + 81 * Math.sin(a)) + 'px';
  $('#tCur').textContent = fmt(player.t); $('#dpTime').textContent = fmt(player.t);
  $('#tDur').textContent = fmt(player.dur); $('#dpDur').textContent = fmt(player.dur);
  $('#dpBar').style.width = (p * 100) + '%'; $('#dpKnob').style.left = (p * 100) + '%';
  $('#dpScrub').setAttribute('aria-valuenow', Math.round(p * 100)); $('#dpScrub').setAttribute('aria-valuetext', `${fmt(player.t)} / ${fmt(player.dur)}`);
}
/**
 * Show the playing / paused state everywhere (arm, discs, buttons, mini player).
 * @param {boolean} on True while audio plays
 */
function applyPlaying(on) {
  player.playing = on; player.last = performance.now();
  $('#vinyl').classList.toggle('playing', on);
  $('#tonearm').classList.toggle('down', on);
  $('#deck').classList.toggle('is-playing', on);
  ['#contDisc', '#popDisc', '#dockDiscIcon'].forEach(s => $(s).classList.toggle('spin', on));
  $('#playIcon').className = on ? 'icon-pause' : 'icon-play';
  $('#dpIcon').className = on ? 'icon-pause' : 'icon-play';
  $('#discPop').classList.toggle('playing', on); $('#dpState').textContent = on ? '播放中' : '已暫停';
  $('#dpPlay').setAttribute('aria-label', on ? '暫停' : '播放');
  $('#playBtn').setAttribute('aria-label', on ? '暫停' : '播放');
  $('#nowLabel').textContent = on ? '播放中' : '已暫停';
  updateMini();
  if (on && !tickRaf) tickRaf = requestAnimationFrame(tick);
  if (!on) drawViz(performance.now());
}
/**
 * Play or pause the loaded audio (says so when this lecture has none).
 * @param {boolean} on True to play
 */
function setPlaying(on) {
  if (!player.src) { if (on) showToast('這一講的語音摘要還沒生成，可到「批次排程」確認。', 'warning'); return; }
  if (on) audio.play().catch(e => showToast('無法播放：' + e.message, 'error'));
  else audio.pause();
}
/**
 * Jump to a time in the audio.
 * @param {number} t Seconds
 */
function seek(t) {
  if (!player.src) return;
  const end = player.dur || audio.duration || 0;
  player.t = Math.max(0, Math.min(end || t, t));
  audio.currentTime = player.t;
  renderPlayer();
}
/**
 * Load one audio track into the player (or show that there is none).
 * @param {{src: string, title: string, sub: string, key: string, lecture: (number|null), download: string}|null} info Track
 */
function setTrack(info) {
  player.track = info; player.t = 0; player.dur = 0;
  if (info) {
    player.src = info.src; audio.src = info.src;
    attachAudioResume(audio, info.key);
    $('#audioDl').href = info.download; $('#audioDl').hidden = false;
  } else {
    player.src = ''; audio.removeAttribute('src'); audio.load();
    $('#audioDl').hidden = true;
  }
  $('#playerCard').classList.toggle('no-audio', !info);
  $('#playerEmpty').hidden = !!info;
  $('#audioDone').hidden = !info || info.lecture === null;
  const title = info ? info.title : '語音摘要', sub = info ? info.sub : '';
  $('#trackTitle').textContent = title; $('#dpTitle').textContent = title;
  $('#trackSub').textContent = sub; $('#dpSub').textContent = sub;
  const tt = $('#trackTitle'); tt.classList.remove('swap'); void tt.offsetWidth; tt.classList.add('swap');
  renderPlayer();
}
/**
 * Load the current lecture's newest audio overview, unless something is playing (it keeps playing).
 * @param {boolean} [force] Load even while playing
 */
function loadLectureAudio(force = false) {
  if (player.playing && !force) return;
  const course = currentStudyCourse;
  if (!course) { setTrack(null); return; }
  const no = activeStudyLectureNo, isCourse = no === null;
  const job = (course.jobs || [])
    .filter(j => j.artifact_type === (isCourse ? 'course_audio' : 'audio') && j.output_file && ['done', 'needs_review'].includes(j.status)
      && (isCourse ? j.lecture_no === null : j.lecture_no === no))
    .sort((a, b) => (b.version || 1) - (a.version || 1))[0];
  if (!job) { setTrack(null); $('#trackSub').textContent = `${course.code}　·　${lectureName(no)}`; return; }
  const path = job.rel_path || job.output_file.split('/').pop();
  const src = `/api/artifacts/${course.code}/download/${encodeURIComponent(path)}`;
  if (player.src === src) return;
  setTrack({
    src, download: src, lecture: no, key: `audio:${course.code}:${isCourse ? 'course' : no}`,
    title: isCourse ? '全課統整語音' : lectureTopic(no) || lectureName(no),
    sub: `${course.code}　·　${lectureName(no)}`,
  });
}
/**
 * Move to the previous or next lecture's audio (keeps playing when it was playing).
 * @param {number} step -1 for the previous lecture, 1 for the next
 */
function stepLecture(step) {
  if (!currentStudyCourse) return;
  const nos = (currentStudyCourse.lectures || []).map(l => l.no);
  const now = player.track ? player.track.lecture : activeStudyLectureNo;
  const i = nos.indexOf(now), target = nos[i + step];
  if (target === undefined) { notify(step < 0 ? '已經是第一講' : '已經是最後一講'); return; }
  const wasPlaying = player.playing;
  if (wasPlaying) { audio.pause(); applyPlaying(false); }
  selectStudyLecture(target);
  loadLectureAudio(true);
  if (wasPlaying && player.src) audio.play().catch(() => {});
}
audio.addEventListener('play', () => applyPlaying(true));
audio.addEventListener('pause', () => applyPlaying(false));
audio.addEventListener('loadedmetadata', () => { player.dur = audio.duration || 0; audio.playbackRate = player.speed; renderPlayer(); });
audio.addEventListener('timeupdate', () => { if (!player.playing) { player.t = audio.currentTime; renderPlayer(); } });
audio.addEventListener('ended', () => {
  applyPlaying(false);
  if (player.track && player.track.lecture !== null) markStep('audio');
  $('#toast').classList.add('show');
});
audio.addEventListener('error', () => { if (player.src) showToast('音檔讀取失敗，可能已被移動或刪除。', 'error'); });

$('#playBtn').addEventListener('click', () => setPlaying(!player.playing));
/**
 * Open or close the mini player next to the Dock record.
 * @param {boolean} open True to open
 */
function setDiscPop(open) { $('#discPop').classList.toggle('open', open); $('#dockDisc').setAttribute('aria-expanded', open); updateMini(); }
$('#dockDisc').addEventListener('click', e => { e.stopPropagation(); setDiscPop(!$('#discPop').classList.contains('open')); });
$('#dpPlay').addEventListener('click', () => setPlaying(!player.playing));
[['#dpBack', '#back15'], ['#dpPrev', '#prevSec'], ['#dpNext', '#nextSec'], ['#dpFwd', '#fwd15']].forEach(([a, b]) => $(a).addEventListener('click', () => $(b).click()));
$('#dpSpeed').addEventListener('click', () => {
  const rates = ['0.75', '1', '1.25', '1.5', '2'], i = rates.indexOf(String(player.speed));
  setChoice('speed', rates[(i + 1) % rates.length]);
});
(() => {
  // drag or click the progress bar; arrow keys step 15 seconds
  const sc = $('#dpScrub'), at = x => { const r = $('.dp-track', sc).getBoundingClientRect(); seek(Math.max(0, Math.min(1, (x - r.left) / r.width)) * player.dur); };
  sc.addEventListener('pointerdown', e => { try { sc.setPointerCapture(e.pointerId); } catch (err) {} sc.classList.add('dragging'); at(e.clientX); });
  sc.addEventListener('pointermove', e => { if (sc.classList.contains('dragging')) at(e.clientX); });
  sc.addEventListener('pointerup', () => sc.classList.remove('dragging'));
  sc.addEventListener('keydown', e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); seek(player.t + (e.key === 'ArrowLeft' ? -15 : 15)); } });
})();
$('#dpGo').addEventListener('click', () => {
  if (player.playing && currentView !== 'studio') { backToPlayer(); return; }
  setDiscPop(false); showView('studio'); setChoice('studioPane', 'study', false);
  const ps = $('#paneStudy'); if (ps.classList.contains('side-collapsed')) $(':scope > .col-resizer .col-toggle', ps).click();
});
document.addEventListener('click', e => { if (!e.target.closest('.dock-disc-wrap') && $('#discPop').classList.contains('open')) setDiscPop(false); });
$('#back15').addEventListener('click', () => seek(player.t - 15));
$('#fwd15').addEventListener('click', () => seek(player.t + 15));
$('#prevSec').addEventListener('click', () => stepLecture(-1));
$('#nextSec').addEventListener('click', () => stepLecture(1));
$('#audioDone').addEventListener('click', () => markStep('audio'));

/* Speed menu inside the transport: closes on choice, outside click or Esc */
const speedMenu = $('#speedMenu');
/**
 * Open or close the speed menu in the transport.
 * @param {boolean} open True to open
 */
function setSpeedMenu(open) { speedMenu.classList.toggle('open', open); $('#speedBtn').setAttribute('aria-expanded', open); }
$('#speedBtn').addEventListener('click', e => { e.stopPropagation(); setSpeedMenu(!speedMenu.classList.contains('open')); });
speedMenu.addEventListener('click', e => { const b = e.target.closest('button'); if (b) { setChoice('speed', b.dataset.v); setSpeedMenu(false); } });
document.addEventListener('click', e => { if (!e.target.closest('.speed-wrap')) setSpeedMenu(false); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') setSpeedMenu(false); });

/* Visual switching: segmented pill, click-to-flip, ambient horizon */
const skins = ['vinyl', 'sine', 'ring', 'led'];
let skin = 'vinyl', flipOn = true;
/** Class + content for a small record in the current visual. */
const miniClass = () => (skin === 'vinyl' ? 'vinyl-icon' : `mini-viz mv-${skin}`);
/** Make every small record (overview, Dock, now-playing card) show the current visual. */
function renderMiniDiscs() {
  ['#contDisc', '#popDisc', '#dockDiscIcon'].forEach(sel => {
    const el = $(sel); if (!el) return;
    el.className = miniClass() + (player.playing ? ' spin' : '');
    el.innerHTML = skin === 'vinyl' ? '' : '<canvas aria-hidden="true"></canvas>';
    sizeMini(el);
  });
  drawViz(performance.now());
}
/**
 * Size a mini record's canvas to its --d diameter at device resolution.
 * @param {HTMLElement} el Mini record element
 */
function sizeMini(el) {
  const c = $('canvas', el); if (!c) return;
  const d = parseFloat(getComputedStyle(el).getPropertyValue('--d')) || el.offsetWidth || 44, dpr = window.devicePixelRatio || 1;
  c.width = Math.round(d * dpr); c.height = Math.round(d * dpr);
}
/**
 * Switch the player visual (vinyl, sine, ring, LED) on the turntable and every small record.
 * @param {string} v Visual id
 */
function setSkin(v) {
  skin = v;
  $$('#visual .skin').forEach(s => s.classList.toggle('on', s.dataset.skin === v));
  sizeCanvases();
  renderMiniDiscs();
}
$('#visual').addEventListener('click', () => {
  if (!flipOn) return;
  const vis = $('#visual'); vis.classList.add('flipping');
  setTimeout(() => { setChoice('skin', skins[(skins.indexOf(skin) + 1) % skins.length]); vis.classList.remove('flipping'); }, 300);
});

/* Canvas visualizers: animate only while playing (motion stops when the step ends) */
let C = { accent: '#3f8f6b', ink: '#fff' };
/**
 * Read the palette colours used by the canvas visuals, then redraw.
 */
function vizColors() {
  requestAnimationFrame(() => {
    const cs = getComputedStyle(root);
    C.accent = cs.getPropertyValue('--accent').trim();
    C.ink = root.dataset.mode === 'dark' ? 'rgba(255,255,255,.18)' : 'rgba(0,0,0,.12)';
    drawViz(performance.now());
  });
}
/**
 * Size every visual canvas to its box at device resolution, then redraw.
 */
function sizeCanvases() {
  const dpr = window.devicePixelRatio || 1;
  $$('canvas.viz').forEach(c => { const w = c.offsetWidth, h = c.offsetHeight; if (w) { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); } });
  drawViz(performance.now());
}
/**
 * Smooth pseudo-random level for one bar of the spectrum visuals.
 * @param {number} i Bar index
 * @param {number} t Time in milliseconds
 * @returns {number} Level between 0.35 and 1
 */
const energy = (i, t) => 0.35 + 0.65 * Math.abs(Math.sin(i * 0.37 + t * 0.0021) * Math.cos(i * 0.11 - t * 0.0013));
/** Draw the current visual on its disc (crisp at any pixel density); still when paused. */
/**
 * Draw the current visual on its disc and on every small record (still when paused).
 * @param {number} now Animation time in milliseconds
 */
function drawViz(now) {
  const t = player.playing ? now : 0, amp = player.playing ? 1 : 0.28, dpr = window.devicePixelRatio || 1;
  const big = $('#visual .skin.on canvas.viz');
  if (big && skin !== 'vinyl' && big.width) paintSkin(big, t, amp);
  if (skin !== 'vinyl') $$('.mini-viz canvas').forEach(c => { if (c.width && (c.closest('.fly-disc') || c.offsetParent)) paintSkin(c, t, amp); });
  drawHorizon(t, amp, dpr);
}
/**
 * Paint one visual on a canvas; sizes scale with the canvas (k = 1 at the 144px player disc), so every size is the same picture.
 * @param {HTMLCanvasElement} c Canvas
 * @param {number} t Time in milliseconds (0 when paused)
 * @param {number} amp Amplitude (1 playing, 0.28 paused)
 */
function paintSkin(c, t, amp) {
  {
    const g = c.getContext('2d'), w = c.width, h = c.height, cx = w / 2, cy = h / 2, R = w / 2, dpr = w / 144;
    g.clearRect(0, 0, w, h);
    if (skin === 'sine') {
      // faint guide rings, then three glowing waves that taper at the edges of the disc
      g.strokeStyle = 'rgba(255,255,255,.05)'; g.lineWidth = dpr;
      [0.38, 0.64, 0.9].forEach(k => { g.beginPath(); g.arc(cx, cy, R * k, 0, Math.PI * 2); g.stroke(); });
      g.save(); g.shadowColor = C.accent; g.shadowBlur = 8 * dpr; g.lineCap = 'round';
      for (let k = 0; k < 3; k++) {
        g.beginPath(); g.lineWidth = (2 - k * 0.5) * dpr; g.strokeStyle = C.accent; g.globalAlpha = 1 - k * 0.32;
        const x0 = w * 0.1, x1 = w * 0.9;
        for (let x = x0; x <= x1; x += dpr) {
          const u = (x - x0) / (x1 - x0), env = Math.pow(Math.sin(Math.PI * u), 1.6);
          const y = cy + env * amp * h * (0.19 - k * 0.045) * Math.sin(u * (4 + k * 1.5) * Math.PI + t * 0.0022 * (1 + k * 0.35) + k * 1.3);
          if (x === x0) g.moveTo(x, y); else g.lineTo(x, y);
        }
        g.stroke();
      }
      g.restore();
    } else if (skin === 'ring') {
      // a record-style label in the centre, fine bars radiating from it
      const r0 = R * 0.42, n = 72;
      g.save(); g.lineCap = 'round'; g.lineWidth = 2 * dpr;
      for (let i = 0; i < n; i++) {
        const a = i / n * Math.PI * 2 - Math.PI / 2, e = player.playing ? energy(i, t) : 0.16 + 0.04 * Math.sin(i);
        const len = R * 0.42 * e;
        g.strokeStyle = C.accent; g.globalAlpha = 0.35 + 0.65 * e;
        g.beginPath(); g.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0); g.lineTo(cx + Math.cos(a) * (r0 + len), cy + Math.sin(a) * (r0 + len)); g.stroke();
      }
      g.restore();
      g.fillStyle = '#1b211d'; g.beginPath(); g.arc(cx, cy, R * 0.36, 0, Math.PI * 2); g.fill();
      g.strokeStyle = 'rgba(255,255,255,.28)'; g.lineWidth = dpr; g.beginPath(); g.arc(cx, cy, R * 0.36, 0, Math.PI * 2); g.stroke();
      g.strokeStyle = 'rgba(255,255,255,.1)'; g.beginPath(); g.arc(cx, cy, R * 0.26, 0, Math.PI * 2); g.stroke();
      const sp = g.createRadialGradient(cx, cy, 0, cx, cy, R * 0.07); sp.addColorStop(0, '#e2c08d'); sp.addColorStop(0.7, '#a4783c'); sp.addColorStop(1, '#523b18');
      g.fillStyle = sp; g.beginPath(); g.arc(cx, cy, R * 0.07, 0, Math.PI * 2); g.fill();
    } else if (skin === 'led') {
      // a round dot-matrix meter: columns light up from the bottom, unlit dots stay as a faint grid
      const step = 7.5 * dpr, rDot = 2.1 * dpr, inner = R - 9 * dpr, cols = Math.floor((inner * 2) / step);
      const startX = cx - (cols - 1) * step / 2;
      for (let i = 0; i < cols; i++) {
        const x = startX + i * step, half = Math.sqrt(Math.max(0, inner * inner - (x - cx) ** 2));
        const top = cy - half, bottom = cy + half, e = player.playing ? energy(i * 2.3, t) : 0.2 + 0.05 * Math.sin(i * 1.7);
        const litTop = bottom - (bottom - top) * e;
        for (let y = bottom - step / 2; y >= top + step / 2 - 0.5; y -= step) {
          const lit = y >= litTop;
          if (lit) { g.fillStyle = C.accent; g.globalAlpha = 0.22; g.beginPath(); g.arc(x, y, rDot * 1.9, 0, Math.PI * 2); g.fill(); g.globalAlpha = 0.6 + 0.4 * ((bottom - y) / (bottom - top)); }
          else { g.fillStyle = '#ffffff'; g.globalAlpha = 0.07; }
          g.beginPath(); g.arc(x, y, rDot, 0, Math.PI * 2); g.fill();
        }
      }
      g.globalAlpha = 1;
    }
  }
}
/**
 * Draw the optional ambient wave under the vinyl.
 * @param {number} t Time in milliseconds (0 when paused)
 * @param {number} amp Amplitude (1 playing, 0.28 paused)
 * @param {number} dpr Device pixel ratio
 */
function drawHorizon(t, amp, dpr) {
  const hz = $('#horizonCanvas');
  if ($('#deck').classList.contains('with-horizon') && skin === 'vinyl' && hz.width) {
    const g = hz.getContext('2d'), w = hz.width, h = hz.height; g.clearRect(0, 0, w, h);
    g.strokeStyle = C.accent; g.lineWidth = 1.5 * dpr;
    for (let k = 0; k < 2; k++) {
      g.globalAlpha = 0.7 - k * 0.3; g.beginPath();
      for (let x = 0; x <= w; x += 2) { const y = h / 2 + Math.sin(Math.PI * x / w) * amp * h * 0.32 * Math.sin(x / w * 10 * Math.PI + t * 0.0025 + k * 1.4); if (x) g.lineTo(x, y); else g.moveTo(x, y); }
      g.stroke();
    }
    g.globalAlpha = 1;
  }
}
/* The player loop only runs while audio plays, so a paused page uses no animation frames */
let tickRaf = 0;
/**
 * One animation frame while playing: read the audio clock, move the arc, draw the visual.
 * @param {number} now Animation time in milliseconds
 */
function tick(now) {
  tickRaf = 0;
  if (!player.playing) return;
  player.t = audio.currentTime; if (audio.duration) player.dur = audio.duration;
  renderPlayer();
  drawViz(now);
  if (player.playing) tickRaf = requestAnimationFrame(tick);
}
$('#toastLater').addEventListener('click', () => $('#toast').classList.remove('show'));
$('#toastGo').addEventListener('click', () => { $('#toast').classList.remove('show'); switchStudyTab('quiz'); $('#bench').scrollIntoView({ behavior: 'smooth' }); });
