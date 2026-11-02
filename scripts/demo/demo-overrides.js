/* Gemini Notebook 學習工作室 — demo-only adjustments, loaded after the app's own scripts in docs/demo/index.html.
   Things the real app gets from files on this computer come from the page instead: the audio overview and
   the lecture PDFs are embedded (DEMO_AUDIO, DEMO_PDFS from scripts/build_demo.py), report-style outputs
   are drawn from the fictional course content, and downloads explain that they need the local app. */

/**
 * The embedded PDF of a lecture as a blob URL (made once per lecture).
 * @param {string} code Course code
 * @param {number} no Lecture number
 * @returns {string} Blob URL
 */
function demoPdf(code, no) {
  demoPdf.cache = demoPdf.cache || {};
  const key = `${code}|${no}`;
  if (!demoPdf.cache[key]) {
    const b64 = (DEMO_PDFS[code] || {})[no] || (DEMO_PDFS.BIO101 || {})[1];
    const bytes = Uint8Array.from(atob(b64), ch => ch.charCodeAt(0));
    demoPdf.cache[key] = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
  }
  return demoPdf.cache[key];
}

/* Audio: every lecture plays the embedded sample track */
const demoSetTrack = setTrack;
setTrack = info => demoSetTrack(info ? { ...info, src: DEMO_AUDIO, download: DEMO_AUDIO } : info);
$('#audioDl').addEventListener('click', e => { e.preventDefault(); demoNote('下載音檔'); });

/* Downloads need the real files */
downloadWeaknessAnki = () => demoNote('匯出 Anki CSV');
downloadFlashcardsAnki = () => demoNote('下載 Anki CSV');

/**
 * The fictional lecture currently open.
 * @returns {{course: object, lec: object|null, no: number|null}} Course, lecture and number
 */
function demoCurrent() {
  const course = demoCourse(currentStudyCourse.code), no = activeStudyLectureNo;
  return { course, lec: no === null ? null : course.lectures[no - 1], no };
}

/**
 * Report-style content for one viewer kind, drawn from the fictional course.
 * @param {string} kind Key of REPORT_KINDS
 * @returns {string} HTML
 */
function demoReportHTML(kind) {
  const { course, lec, no } = demoCurrent();
  const lectures = lec ? [lec] : course.lectures;
  const title = lec ? `第 ${demoPad(no)} 講　${lec.topic}` : `${course.name}　全課`;
  const points = lectures.flatMap(l => [...l.points, ...(l.laterPoints || [])]);
  const terms = lectures.flatMap(l => l.cards);
  if (kind === 'mindmap') {
    const items = terms.slice(0, 6);
    const nodes = items.map((t, i) => {
      const a = (i / items.length) * Math.PI * 2 - Math.PI / 2, x = 280 + Math.cos(a) * 190, y = 150 + Math.sin(a) * 105;
      return `<path d="M280 150 L${x} ${y}" stroke="var(--h-mindmap)" stroke-width="1.5" opacity=".6"/><rect x="${x - 56}" y="${y - 16}" width="112" height="32" rx="16" fill="var(--surface)" stroke="var(--line)"/><text x="${x}" y="${y + 5}" text-anchor="middle" font-size="13" fill="currentColor">${t[0]}</text>`;
    }).join('');
    return `<svg viewBox="0 0 560 300" style="width:100%;max-width:720px;display:block;margin:auto;color:var(--ink)">${nodes}<rect x="210" y="132" width="140" height="36" rx="18" fill="var(--h-mindmap)"/><text x="280" y="155" text-anchor="middle" font-size="14" fill="#fff">${lec ? lec.topic : course.name}</text></svg>`;
  }
  if (kind === 'table') {
    return `<div class="reader"><table><thead><tr><th>名詞</th><th>重點</th></tr></thead><tbody>${terms.map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join('')}</tbody></table></div>`;
  }
  if (kind === 'infographic') {
    return `<div style="max-width:420px;margin:auto;border-radius:16px;padding:24px;background:linear-gradient(160deg,var(--h-infographic),var(--h-report));color:#fff">
      <div style="font-size:12px;opacity:.8">${course.code}　資訊圖表</div><h3 style="font-size:22px;margin:4px 0 16px">${title}</h3>
      ${terms.slice(0, 5).map(([a, b]) => `<div style="background:rgba(255,255,255,.14);border-radius:12px;padding:12px 16px;margin-bottom:8px"><b>${a}</b><div style="font-size:13px;opacity:.9">${b}</div></div>`).join('')}</div>`;
  }
  if (kind === 'slides') {
    return `<div style="aspect-ratio:16/9;max-width:720px;margin:auto;border-radius:12px;background:var(--surface);box-shadow:var(--shadow);padding:40px;display:flex;flex-direction:column;justify-content:center;gap:12px">
      <div class="eyebrow">${course.code}　投影片 1 / ${terms.length + 1}</div><h3 style="font-size:28px">${title}</h3><p class="muted">${terms.map(t => t[0]).join('・')}</p></div>`;
  }
  if (kind === 'video') {
    return `<div class="empty-state">示範版不含影片。<br>本機版會在這裡直接播放 Gemini Notebook 生成的影片摘要。</div>`;
  }
  const names = { guide: '讀書指南', concept: '概念解說', briefing: '簡報文件', blog: '部落格文章' };
  return `<div class="reader" style="max-width:760px"><h1>${names[kind] || '報告'}：${lec ? lec.topic : course.name}</h1>
    <p>這份${names[kind] || '報告'}整理${lec ? '這一講' : '整門課'}最重要的觀念。先讀重點，再用下面的名詞自我測驗：遮住右邊，說說看它是什麼。</p>
    <h3>重點</h3><ul>${points.map(p => `<li>${p.note}<br><span class="small muted">${p.quote}</span></li>`).join('') || '<li>這一講的重點會在講義「產生重點」後出現。</li>'}</ul>
    <h3>名詞</h3><table><tbody>${terms.map(([a, b]) => `<tr><td style="width:30%"><b>${a}</b></td><td>${b}</td></tr>`).join('')}</tbody></table>
    <blockquote>自我檢查：不看講義，你能用三句話說出${lec ? '這一講' : '這門課'}在講什麼嗎？</blockquote></div>`;
}

/**
 * Show one report-style output in the workbench (demo version of the app's viewer).
 * @param {string} kind Key of REPORT_KINDS
 */
loadReportInViewer = async function (kind) {
  const group = currentReportGroup.includes(kind) ? currentReportGroup : [kind];
  $('#reportKindButtons').innerHTML = group.length > 1 ? group.map(key =>
    `<button class="chip${key === kind ? ' on' : ''}" style="--hue:var(--h-report)" onclick="loadReportInViewer('${key}')">${REPORT_KINDS[key].label}</button>`).join('') : '';
  const job = pickLatestJob(REPORT_KINDS[kind].types);
  const box = $('#reportContentContainer');
  if (!job) { box.innerHTML = `<div class="empty-state">${activeStudyLectureNo === null ? '整門課' : '這一講'}還沒有「${REPORT_KINDS[kind].label}」。</div>`; return; }
  const readable = ['guide', 'concept'].includes(kind) && activeStudyLectureNo !== null;
  box.innerHTML = `<div class="report-meta"><span class="tag">v${job.version || 1}</span><span class="small muted">示範內容</span><span class="spacer"></span>${readable ? '<button class="btn btn-soft btn-sm" onclick="markStep(\'guide\')">我讀完了</button>' : ''}</div>` + demoReportHTML(kind);
};

/* The OpenAPI link points at the local server */
document.querySelectorAll('a[href="/docs"]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); demoNote('OpenAPI 文件'); }));
