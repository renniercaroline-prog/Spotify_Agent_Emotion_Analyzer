"""Render results -> a single self-contained interactive dashboard.html.

All data is inlined as JSON; the only external dependency is Chart.js via CDN.
Built around the 25 curated GEMS emotions (no clusters in the UI). The file opens
by double-click and is deployable as a static page (GitHub Pages).
"""
from __future__ import annotations

import argparse
import json
import math


def _json_safe(o):
    """Recursively replace NaN/Infinity (invalid JSON) with None so the browser's
    JSON.parse never chokes — happens when a listener has unscored tracks."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    return o


def build_html(results: dict) -> str:
    data_json = json.dumps(_json_safe(results), ensure_ascii=False,
                           allow_nan=False).replace("</", "<\\/")
    return _TEMPLATE.replace("/*__DATA__*/", data_json)


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Emotional Listening Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#0e1117; --panel:#161b22; --panel2:#1c232c; --line:#2a323d;
    --text:#e6edf3; --muted:#9aa7b4; --accent:#7c5cff;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.5}
  .wrap{max-width:1120px;margin:0 auto;padding:28px 20px 80px}
  header h1{margin:0 0 4px;font-size:30px;letter-spacing:-0.5px}
  header .range{color:var(--muted);font-size:15px}
  .totals{display:flex;flex-wrap:wrap;gap:14px;margin:20px 0 10px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;
    padding:14px 18px;min-width:120px;flex:1}
  .stat .num{font-size:26px;font-weight:700}
  .stat .lbl{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
  .narrative{background:linear-gradient(135deg,rgba(124,92,255,.10),rgba(72,202,228,.06));
    border:1px solid var(--line);border-radius:14px;padding:18px 22px;margin-top:16px;
    font-size:17px;line-height:1.6}
  section{margin-top:38px}
  h2{font-size:20px;margin:0 0 4px;display:flex;align-items:center;gap:10px}
  .sub{color:var(--muted);font-size:13px;margin:0 0 16px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
  @media(max-width:820px){.grid2{grid-template-columns:1fr}}
  .findings{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  @media(max-width:820px){.findings{grid-template-columns:1fr}}
  .card{background:var(--panel);border:1px solid var(--line);border-left-width:4px;
    border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
  .card .rank{font-size:12px;color:var(--muted)}
  .card .txt{font-size:15px}
  .card .txt em{font-style:normal;font-weight:700}
  .card .meta{font-size:12px;color:var(--muted)}
  .card canvas{width:100%!important;height:46px!important}
  .controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
  select,button{background:var(--panel2);color:var(--text);border:1px solid var(--line);
    border-radius:8px;padding:7px 10px;font-size:13px;cursor:pointer}
  select[multiple]{min-width:220px;height:150px}
  .chip{display:inline-flex;gap:6px;flex-wrap:wrap}
  .chip button{font-size:12px;padding:4px 9px;border-radius:16px}
  .chip button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  .chartbox{position:relative;height:340px}
  .chartbox.tall{height:460px}
  .small{height:230px}
  table{width:100%;border-collapse:collapse;font-size:13px}
  td,th{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line)}
  th{color:var(--muted);font-weight:600}
  footer{margin-top:50px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);
    padding-top:18px}
  .pill{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;
    background:var(--panel2);border:1px solid var(--line);color:var(--muted)}
  .chip2{display:inline-block;padding:2px 9px;border-radius:14px;font-size:11px;font-weight:600;
    white-space:nowrap}
  .defcards{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
  @media(max-width:820px){.defcards{grid-template-columns:1fr 1fr}}
  .defcard{background:var(--panel);border:1px solid var(--line);border-top-width:3px;
    border-radius:12px;padding:14px}
  .defcard .part{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
  .defcard .tk{font-weight:700;margin:6px 0 2px;line-height:1.3}
  .defcard .ar{color:var(--muted);font-size:13px;margin-bottom:9px}
  td .num2{color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1 id="title"></h1>
    <div class="range" id="range"></div>
  </header>
  <div class="totals" id="totals"></div>

  <div class="narrative" id="narrative"></div>

  <section>
    <h2>★ Most surprising findings</h2>
    <p class="sub">Ranked by effect size and reliability, validated with permutation tests.
      Each shows how a slice of listening differs from this person's own yearly average.</p>
    <div class="findings" id="findings"></div>
  </section>

  <section>
    <h2>Overall emotional fingerprint</h2>
    <p class="sub">Minutes-weighted average intensity of each of the 25 emotions across all
      listening.</p>
    <div class="panel"><div class="chartbox tall"><canvas id="radar"></canvas></div></div>
  </section>

  <section>
    <h2>The emotional clock</h2>
    <p class="sub">How chosen emotions rise and fall across the 24-hour day
      (minutes-weighted). Dashed line is the yearly average.</p>
    <div class="controls"><label>Show:</label><select id="clockSelect" multiple></select>
      <span class="pill">⌘/Ctrl-click to pick several</span></div>
    <div class="panel"><div class="chartbox"><canvas id="clock"></canvas></div></div>
  </section>

  <section>
    <h2>Day of week &amp; weekend</h2>
    <p class="sub">Deviation of each day from the yearly average for the chosen emotion.</p>
    <div class="controls"><label>Emotion:</label><select id="dowSelect"></select></div>
    <div class="grid2">
      <div class="panel"><div class="chartbox small"><canvas id="dow"></canvas></div></div>
      <div class="panel"><div class="chartbox small"><canvas id="weekend"></canvas></div></div>
    </div>
  </section>

  <section>
    <h2>Across the year</h2>
    <p class="sub">Monthly trajectory of chosen emotions, with seasons shaded.
      Faint X markers flag partial first/last months.</p>
    <div class="controls"><label>Show:</label><select id="yearSelect" multiple></select></div>
    <div class="panel"><div class="chartbox tall"><canvas id="year"></canvas></div></div>
  </section>

  <section>
    <h2>Seasonal profiles</h2>
    <p class="sub">How each season differs from the yearly average. The middle ring is the
      average; pushing outward means more than usual that season, toward the centre means
      less.</p>
    <div class="controls"><label>Season:</label><select id="seasonSelect"></select></div>
    <div class="panel"><div class="chartbox tall"><canvas id="season"></canvas></div></div>
  </section>

  <section>
    <h2>Your top tracks &amp; artists</h2>
    <p class="sub">Most-played by listening time, each tagged with its dominant emotion.</p>
    <div class="grid2">
      <div class="panel"><h3 style="margin:0 0 8px;font-size:14px">Top tracks</h3>
        <table id="lbTracks"></table></div>
      <div class="panel"><h3 style="margin:0 0 8px;font-size:14px">Top artists</h3>
        <table id="lbArtists"></table></div>
    </div>
  </section>

  <section>
    <h2>Songs that defined your day</h2>
    <p class="sub">The track you played most in each part of the day — and the feeling it carries.</p>
    <div class="defcards" id="defCards"></div>
  </section>

  <section>
    <h2>Signature tracks by emotion</h2>
    <p class="sub">The tracks and artists that most embody each emotion in this listening
      history.</p>
    <div class="controls"><label>Emotion:</label><select id="sigSelect"></select></div>
    <div class="grid2">
      <div class="panel"><h3 style="margin:0 0 8px;font-size:14px">Top tracks</h3>
        <table id="sigTracks"></table></div>
      <div class="panel"><h3 style="margin:0 0 8px;font-size:14px">Top artists</h3>
        <table id="sigArtists"></table></div>
    </div>
  </section>

  <footer id="footer"></footer>
</div>

<script id="data" type="application/json">/*__DATA__*/</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const T = DATA.taxonomy, B = DATA.baseline, P = DATA.profiles;
const EMOS = T.emotions;
Chart.defaults.color = '#9aa7b4';
Chart.defaults.borderColor = '#2a323d';
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;

const color = e => T.emotion_colors[e] || '#7c5cff';
const label = e => T.emotion_labels[e] || e;
function hexA(hex,a){const n=parseInt(hex.slice(1),16);
  return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`;}

/* ---------- header ---------- */
const m = DATA.meta;
document.getElementById('title').textContent = `${m.name}'s Emotional Listening Year`;
document.getElementById('range').textContent =
  `${m.date_start} → ${m.date_end}  ·  ${m.n_emotions} emotions  ·  ${m.coverage_plays_pct}% of plays scored`;
[['Hours',m.total_hours.toLocaleString()],['Plays',m.total_plays.toLocaleString()],
 ['Tracks',m.unique_tracks.toLocaleString()],['Artists',m.unique_artists.toLocaleString()]]
  .forEach(([l,n])=>{ document.getElementById('totals').innerHTML +=
    `<div class="stat"><div class="num">${n}</div><div class="lbl">${l}</div></div>`; });
if(DATA.narrative) document.getElementById('narrative').textContent = DATA.narrative;

/* ---------- findings ---------- */
function findingSpark(canvas, f){
  const prof = P[f.dimension]; if(!prof) return;
  const vals = prof.buckets.map(b => b.emotions[f.emotion]);
  const labels = prof.buckets.map(b => b.label);
  const hi = labels.indexOf(String(f.bucket));
  new Chart(canvas, {type:'bar', data:{labels, datasets:[{data:vals,
    backgroundColor: labels.map((_,i)=> i===hi ? f.color : hexA(f.color,0.22)),
    borderWidth:0, barPercentage:1, categoryPercentage:0.92}]},
    options:{plugins:{legend:{display:false},tooltip:{enabled:false}},
      scales:{x:{display:false},y:{display:false,
        suggestedMin:Math.min(...vals)*0.9, suggestedMax:Math.max(...vals)*1.05}},
      animation:false, maintainAspectRatio:false}});
}
DATA.findings.forEach((f,i)=>{
  const div = document.createElement('div');
  div.className = 'card'; div.style.borderLeftColor = f.color;
  div.innerHTML = `<div class="rank">#${i+1} · ${f.dim_label}</div>
    <div class="txt">${f.sentence.replace(/\*(.+?)\*/g,'<em>$1</em>')}</div>
    <canvas></canvas>
    <div class="meta">${Math.round(f.minutes).toLocaleString()} min · ${f.plays} plays
      · z=${f.z} · p${f.p_value<0.001?'<0.001':'='+f.p_value}</div>`;
  document.getElementById('findings').appendChild(div);
  findingSpark(div.querySelector('canvas'), f);
});

/* ---------- fingerprint radar (all 25) ---------- */
new Chart(document.getElementById('radar'), {
  type:'radar',
  data:{labels:EMOS.map(label), datasets:[{label:'Average intensity',
    data:EMOS.map(e=>B.emotions[e]), backgroundColor:hexA('#7c5cff',0.16),
    borderColor:'#7c5cff', pointBackgroundColor:EMOS.map(color),
    pointBorderColor:EMOS.map(color), pointRadius:3, borderWidth:2}]},
  options:{maintainAspectRatio:false,
    scales:{r:{suggestedMin:0, ticks:{backdropColor:'transparent',stepSize:0.1},
      grid:{color:'#2a323d'}, angleLines:{color:'#2a323d'},
      pointLabels:{font:{size:10}}}},
    plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>`${c.label}: ${c.raw.toFixed(3)}`}}}}});

/* ---------- emotional clock ---------- */
let clockChart;
function drawClock(){
  const sel = [...document.getElementById('clockSelect').selectedOptions].map(o=>o.value);
  const hours = P.hour.buckets;
  const labels = hours.map(b => `${b.label}:00`);
  const datasets = [];
  sel.forEach(e=>{ const col=color(e);
    datasets.push({label:label(e), data:hours.map(b=>b.emotions[e]), borderColor:col,
      backgroundColor:hexA(col,0.1), tension:0.35, pointRadius:0, borderWidth:2, fill:false});
  });
  sel.forEach(e=>{ const col=color(e);
    datasets.push({label:label(e)+' avg', data:hours.map(()=>B.emotions[e]),
      borderColor:hexA(col,0.5), borderDash:[5,4], pointRadius:0, borderWidth:1, fill:false});
  });
  if(clockChart) clockChart.destroy();
  clockChart = new Chart(document.getElementById('clock'), {type:'line', data:{labels, datasets},
    options:{maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
      scales:{y:{suggestedMin:0,title:{display:true,text:'Avg intensity (0–1)'}},
        x:{ticks:{maxTicksLimit:12}}},
      plugins:{legend:{labels:{filter:i=>!i.text.endsWith(' avg')}}}}});
}

/* ---------- day of week + weekend ---------- */
let dowChart, weekendChart;
function devBars(canvasId, prof, emo, ref){
  const labels = prof.buckets.map(b=>b.label);
  const dev = prof.buckets.map(b => (b.emotions[emo]-ref)/ref*100);
  const col = color(emo);
  return new Chart(document.getElementById(canvasId), {type:'bar',
    data:{labels, datasets:[{data:dev,
      backgroundColor:dev.map(d=> d>=0 ? col : hexA(col,0.45)), borderWidth:0}]},
    options:{maintainAspectRatio:false, plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>`${c.raw>=0?'+':''}${c.raw.toFixed(1)}% vs average`}}},
      scales:{y:{title:{display:true,text:'% vs yearly avg'},ticks:{callback:v=>v+'%'}}}}});
}
function drawDow(){
  const emo = document.getElementById('dowSelect').value;
  const ref = B.emotions[emo];
  if(dowChart) dowChart.destroy(); if(weekendChart) weekendChart.destroy();
  dowChart = devBars('dow', P.day_of_week, emo, ref);
  weekendChart = devBars('weekend', P.weekend_label, emo, ref);
}

/* ---------- across the year ---------- */
const SEASON_BG = {Winter:'rgba(78,168,222,0.07)', Spring:'rgba(72,202,228,0.06)',
  Summer:'rgba(255,209,102,0.07)', Autumn:'rgba(176,137,104,0.08)'};
const MONTHNUM_N = {'01':'Winter','02':'Winter','03':'Spring','04':'Spring','05':'Spring',
  '06':'Summer','07':'Summer','08':'Summer','09':'Autumn','10':'Autumn','11':'Autumn','12':'Winter'};
const MONTHNUM_S = {'01':'Summer','02':'Summer','03':'Autumn','04':'Autumn','05':'Autumn',
  '06':'Winter','07':'Winter','08':'Winter','09':'Spring','10':'Spring','11':'Spring','12':'Summer'};
const MONTHNUM = DATA.meta.hemisphere==='south' ? MONTHNUM_S : MONTHNUM_N;
const seasonBands = {id:'seasonBands', beforeDraw(chart){
  const {ctx, chartArea:a, scales:{x}} = chart; if(!a) return;
  const labels = chart.data.labels; ctx.save();
  labels.forEach((lab,i)=>{
    const sea = MONTHNUM[lab.slice(5,7)] || 'Spring';
    const left = i===0 ? a.left : (x.getPixelForValue(i-1)+x.getPixelForValue(i))/2;
    const right = i===labels.length-1 ? a.right : (x.getPixelForValue(i)+x.getPixelForValue(i+1))/2;
    ctx.fillStyle = SEASON_BG[sea] || 'transparent';
    ctx.fillRect(left, a.top, right-left, a.bottom-a.top);
  });
  ctx.restore();
}};
let yearChart;
function drawYear(){
  const sel = [...document.getElementById('yearSelect').selectedOptions].map(o=>o.value);
  const buckets = P.month.buckets;
  const labels = buckets.map(b=>b.label);
  const sorted = buckets.map(b=>b.minutes).slice().sort((a,b)=>a-b);
  const med = sorted[Math.floor(sorted.length/2)];
  const partial = buckets.map(b => b.minutes < med*0.5);
  const datasets = sel.map(e=>{ const col=color(e);
    return {label:label(e), data:buckets.map(b=>b.emotions[e]), borderColor:col,
      backgroundColor:hexA(col,0.08), tension:0.3, borderWidth:2,
      pointRadius:partial.map(p=>p?5:3), pointStyle:partial.map(p=>p?'crossRot':'circle'),
      pointBackgroundColor:col, fill:false};
  });
  if(yearChart) yearChart.destroy();
  yearChart = new Chart(document.getElementById('year'), {type:'line', data:{labels, datasets},
    options:{maintainAspectRatio:false, interaction:{mode:'index',intersect:false},
      scales:{y:{suggestedMin:0,title:{display:true,text:'Avg intensity (0–1)'}}},
      plugins:{legend:{position:'top'}}}, plugins:[seasonBands]});
}

/* ---------- seasonal radar (25 axes, deviation from yearly average) ---------- */
const SEASON_ORDER = ['Spring','Summer','Autumn','Winter'];
const SEASON_PALETTE = {Spring:'#2dd4bf',Summer:'#ffd166',Autumn:'#e07a5f',Winter:'#8aa9ff'};
let seasonChart;
function drawSeason(){
  const byLabel = {}; P.season.buckets.forEach(b=> byLabel[b.label]=b);
  const present = SEASON_ORDER.filter(s=>byLabel[s]);
  const pick = document.getElementById('seasonSelect').value;
  const shown = pick==='all' ? present : present.filter(s=>s===pick);
  const solo = shown.length===1;
  // each axis = (season average − yearly average); zoom to the deviation range so
  // the small seasonal swings are visible instead of buried under the baseline.
  let maxAbs = 0;
  shown.forEach(s=>EMOS.forEach(e=>{
    maxAbs = Math.max(maxAbs, Math.abs(byLabel[s].emotions[e]-B.emotions[e])); }));
  const lim = (maxAbs*1.15) || 0.05;
  const datasets = shown.map(s=>({label:s,
    data:EMOS.map(e=>byLabel[s].emotions[e]-B.emotions[e]), borderColor:SEASON_PALETTE[s],
    backgroundColor:hexA(SEASON_PALETTE[s], solo?0.18:0.05),
    pointRadius:solo?2.5:1.5, borderWidth:2}));
  if(seasonChart) seasonChart.destroy();
  seasonChart = new Chart(document.getElementById('season'), {type:'radar',
    data:{labels:EMOS.map(label), datasets},
    options:{maintainAspectRatio:false,
      scales:{r:{min:-lim, max:lim, ticks:{stepSize:lim/2, backdropColor:'transparent',
          callback:v=> Math.abs(v)<1e-9 ? 'avg' : (v>0?'+':'')+v.toFixed(2)},
        grid:{color:c=> Math.abs(c.tick.value)<1e-9 ? '#5b6675' : '#2a323d'},
        angleLines:{color:'#2a323d'}, pointLabels:{font:{size:10}}}},
      plugins:{legend:{position:'top', display:!solo},
        tooltip:{callbacks:{label:c=>
          `${c.dataset.label}: ${(c.raw>=0?'+':'')+c.raw.toFixed(3)} vs avg`}}}}});
}

/* ---------- leaderboards + song-tied metadata ---------- */
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function emoChip(o){ const c=o.color||'#9aa7b4';
  return `<span class="chip2" style="background:${hexA(c,0.18)};color:${c};`+
    `border:1px solid ${hexA(c,0.5)}">${o.emotion_label||'—'}</span>`; }
(function(){
  const lb = DATA.leaderboards || {tracks:[],artists:[]};
  document.getElementById('lbTracks').innerHTML =
    '<tr><th>#</th><th>Track</th><th>Artist</th><th>Min</th><th>Mood</th></tr>' +
    lb.tracks.map((t,i)=>`<tr><td class="num2">${i+1}</td><td>${esc(t.track)}</td>
      <td>${esc(t.artist)}</td><td class="num2">${Math.round(t.minutes)}</td>
      <td>${emoChip(t)}</td></tr>`).join('');
  document.getElementById('lbArtists').innerHTML =
    '<tr><th>#</th><th>Artist</th><th>Min</th><th>Tracks</th><th>Mood</th></tr>' +
    lb.artists.map((a,i)=>`<tr><td class="num2">${i+1}</td><td>${esc(a.artist)}</td>
      <td class="num2">${Math.round(a.minutes)}</td><td class="num2">${a.tracks}</td>
      <td>${emoChip(a)}</td></tr>`).join('');
  const PART_RANGES = {Night:'12–6am', Morning:'6am–12pm',
                       Afternoon:'12–6pm', Evening:'6pm–12am'};
  document.getElementById('defCards').innerHTML = (DATA.defining_by_part||[]).map(d=>`
    <div class="defcard" style="border-top-color:${d.color}">
      <div class="part">${d.part} · ${PART_RANGES[d.part]||''}</div>
      <div class="tk">${esc(d.track)}</div>
      <div class="ar">${esc(d.artist)}</div>
      ${emoChip(d)}
      <div class="meta" style="margin-top:9px;font-size:12px;color:var(--muted)">
        ${Math.round(d.minutes)} min · ${d.plays} plays</div>
    </div>`).join('');
})();

/* ---------- signature tracks ---------- */
function drawSig(){
  const e = document.getElementById('sigSelect').value;
  const s = DATA.signatures[e] || {tracks:[],artists:[]};
  document.getElementById('sigTracks').innerHTML =
    '<tr><th>Track</th><th>Artist</th><th>Score</th></tr>' +
    s.tracks.map(t=>`<tr><td>${esc(t.track)}</td><td>${esc(t.artist)}</td>
      <td>${t.score.toFixed(2)}</td></tr>`).join('');
  document.getElementById('sigArtists').innerHTML =
    '<tr><th>Artist</th><th>Score</th></tr>' +
    s.artists.map(a=>`<tr><td>${esc(a.artist)}</td>
      <td>${a.score.toFixed(2)}</td></tr>`).join('');
}

/* ---------- selectors ---------- */
const DEFAULTS = ['sorrowful','energetic','nostalgic','calm'].filter(e=>EMOS.includes(e));
function fillSelect(id, defaults){
  const el = document.getElementById(id); el.innerHTML='';
  EMOS.forEach(e=>{ const o=document.createElement('option');
    o.value=e; o.textContent=label(e);
    if(defaults && defaults.includes(e)) o.selected=true;
    el.appendChild(o);
  });
  if(!defaults && !el.value) el.selectedIndex=0;
}
fillSelect('clockSelect', DEFAULTS);
fillSelect('yearSelect', DEFAULTS);
fillSelect('dowSelect', null);
fillSelect('sigSelect', null);
document.getElementById('clockSelect').addEventListener('change', drawClock);
document.getElementById('yearSelect').addEventListener('change', drawYear);
document.getElementById('dowSelect').addEventListener('change', drawDow);
document.getElementById('sigSelect').addEventListener('change', drawSig);

// season selector: "All seasons" plus each season present in the data
(function(){
  const sel = document.getElementById('seasonSelect');
  const present = SEASON_ORDER.filter(s => P.season.buckets.some(b=>b.label===s));
  [['all','All seasons'], ...present.map(s=>[s,s])].forEach(([v,t])=>{
    const o=document.createElement('option'); o.value=v; o.textContent=t; sel.appendChild(o);
  });
  sel.addEventListener('change', drawSeason);
})();

/* ---------- footer ---------- */
document.getElementById('footer').innerHTML =
  `Each track is scored on ${m.n_emotions} emotions from the Geneva Emotional Music Scale (GEMS).
   Scores are <strong>LLM-derived proxies for each track's emotional character</strong>, not
   measured listener feelings. Aggregates are weighted by minutes listened; "average" means this
   person's own yearly minutes-weighted mean. Findings are gated by listening volume and validated
   with permutation tests. Seasons use the ${m.hemisphere}ern hemisphere.`;

/* ---------- init ---------- */
drawClock(); drawDow(); drawYear(); drawSeason(); drawSig();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="results.json -> dashboard.html")
    ap.add_argument("--results", default="results.json")
    ap.add_argument("--out", default="dashboard.html")
    args = ap.parse_args()
    with open(args.results) as f:
        results = json.load(f)
    with open(args.out, "w") as f:
        f.write(build_html(results))
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
