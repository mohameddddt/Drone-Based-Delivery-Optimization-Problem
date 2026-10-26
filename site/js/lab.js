// The order lab: re-fly one drone's stops in any order and compare against every permutation.
/* ---------- order lab ---------- */
const mini = document.getElementById("mini");
const tabs = document.getElementById("tabs");
const picker = document.getElementById("picker");
let cur = 3, seq = [];
const PERMS = ROUTES.map(stops => {
  const all = permutations(stops).map(s => { const ev = evaluate(s, stops); return { s, e: ev.e, d: ev.d, maxLeg: Math.max(...ev.legs.map(l => l.e)) }; });
  return { all, sortedE: all.map(a => a.e).sort((a, b) => a - b), maxLeg: Math.max(...all.map(a => a.maxLeg)), maxE: Math.max(...all.map(a => a.e)), shortest: all.reduce((a, b) => (b.d < a.d ? b : a)) };
});
ROUTES.forEach((stops, r) => {
  const b = document.createElement("button");
  b.type = "button"; b.setAttribute("role", "tab"); b.id = "tab-" + r;
  b.innerHTML = `<i style="border-color:${COLORS[r]}"></i>Drone ${r + 1}`;
  b.addEventListener("click", () => selectRoute(r, true));
  tabs.appendChild(b);
});
el("use", { href: "#basemap" }, mini);
const mGrid = el("g", {}, mini);
el("path", { d: nfPath, class: "nf-fill" }, mGrid);
el("path", { d: nfPath, class: "nf-hatch", "clip-path": "url(#nfclip)" }, mGrid);
el("path", { d: nfPath, class: "nf-line" }, mGrid);
const mLegs = el("g", {}, mini);
const mStops = el("g", {}, mini);
let mk = 1;
function miniScale() {
  const vb = mini.viewBox.baseVal;
  const rect = mini.getBoundingClientRect();
  if (!vb || !rect.width) return;
  mk = Math.max(vb.width / rect.width, vb.height / rect.height);
  rescale(mini, mk);
}
new ResizeObserver(miniScale).observe(mini);

function selectRoute(r, user) {
  cur = r; seq = ROUTES[r].slice();
  [...tabs.children].forEach((b, i) => b.setAttribute("aria-selected", i === r ? "true" : "false"));
  const stops = ROUTES[r];
  const pts = [P[0], ...stops.map(c => P[c])];
  let x0 = Math.min(...pts.map(p => p[0])), x1 = Math.max(...pts.map(p => p[0]));
  let y0 = Math.min(...pts.map(p => p[1])), y1 = Math.max(...pts.map(p => p[1]));
  let w = Math.max(x1 - x0, 120), h = Math.max(y1 - y0, 90);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  if (w / h < 4 / 3) w = h * 4 / 3; else h = w * 3 / 4;
  w *= 1.32; h *= 1.32;
  mini.setAttribute("viewBox", `${cx - w / 2} ${cy - h / 2} ${w} ${h}`);
  mStops.innerHTML = "";
  D.customers.forEach(c => {
    if (stops.includes(c.id)) return;
    const g = scaled(mStops, P[c.id][0], P[c.id][1], "stop other");
    el("circle", { r: 3, class: "dot" }, g);
  });
  const d = scaled(mStops, P[0][0], P[0][1], "depot");
  el("circle", { r: 13, class: "ring" }, d);
  el("circle", { r: 9.5 }, d);
  el("text", { "text-anchor": "middle", y: 4 }, d).textContent = "H";
  stops.forEach(c => {
    const g = scaled(mStops, P[c][0], P[c][1], "stop pick");
    g.dataset.id = c;
    el("circle", { r: 16, class: "hit" }, g);
    el("circle", { r: 8, class: "dot" }, g);
    el("text", { x: 11, y: -9 }, g).textContent = `${c} · ${fmt(dem[c], 2)} kg`;
    el("text", { "text-anchor": "middle", y: 3.2, class: "ord" }, g);
    g.addEventListener("click", () => toggleStop(c));
  });
  picker.innerHTML = "";
  stops.forEach(c => {
    const b = document.createElement("button");
    b.type = "button"; b.dataset.id = c;
    b.innerHTML = `${c} <span>${fmt(dem[c], 2)} kg</span>`;
    b.addEventListener("click", () => toggleStop(c));
    picker.appendChild(b);
  });
  miniScale();
  renderOrder();
}
function toggleStop(c) {
  const i = seq.indexOf(c);
  if (seq.length === ROUTES[cur].length) seq = [];
  if (i === -1 || seq.length === 0) { if (!seq.includes(c)) seq.push(c); }
  else seq = seq.slice(0, i);
  renderOrder();
}
document.querySelectorAll("[data-preset]").forEach(b => b.addEventListener("click", () => {
  const stops = ROUTES[cur], k = b.dataset.preset;
  seq = k === "solver" ? stops.slice() : k === "reverse" ? stops.slice().reverse() : k === "shortest" ? PERMS[cur].shortest.s.slice() : [];
  renderOrder();
}));

function renderOrder() {
  const stops = ROUTES[cur], pm = PERMS[cur], color = COLORS[cur];
  const ev = evaluate(seq, stops);
  // map legs
  mLegs.innerHTML = "";
  ev.legs.forEach(l => {
    const [x1, y1] = P[l.from], [x2, y2] = P[l.to];
    el("line", { x1, y1, x2, y2, class: "leg" + (l.w > 1e-6 ? "" : " empty"), stroke: color, "stroke-width": legWidth(l.w) * 1.15 }, mLegs);
  });
  mStops.querySelectorAll(".stop.pick").forEach(g => {
    const id = +g.dataset.id, k = seq.indexOf(id);
    g.classList.toggle("done", k >= 0);
    g.querySelector(".dot").style.fill = k >= 0 ? color : "";
    g.querySelector(".ord").textContent = k >= 0 ? k + 1 : "";
  });
  [...picker.children].forEach(b => b.setAttribute("aria-pressed", seq.includes(+b.dataset.id) ? "true" : "false"));
  // sequence line
  document.getElementById("seq").innerHTML = ["Depot", ...seq.map(c => `<b>${c}</b>`), ...(ev.complete ? ["Depot"] : Array(stops.length - seq.length).fill("·"))].join(" → ");
  const eEl = document.getElementById("o-e"), dEl = document.getElementById("o-d"), rEl = document.getElementById("o-r");
  const verdict = document.getElementById("verdict");
  eEl.textContent = seq.length ? fmt(ev.e) : "–";
  document.getElementById("o-e-s").textContent = `battery ${fmt(battery)}`;
  dEl.textContent = seq.length ? fmt(ev.d) : "–";
  if (ev.complete) {
    const rank = pm.sortedE.findIndex(x => x >= ev.e - 1e-9) + 1;
    rEl.textContent = "#" + rank;
    document.getElementById("o-r-s").textContent = `of ${pm.all.length} orderings`;
    if (ev.e <= battery + 1e-9) { verdict.className = "verdict ok"; verdict.textContent = `Flyable · uses ${Math.round(ev.e / battery * 100)}% of the battery`; }
    else { verdict.className = "verdict bad"; verdict.textContent = `Over the battery by ${fmt(ev.e - battery)} · infeasible`; }
  } else {
    rEl.textContent = "–";
    document.getElementById("o-r-s").textContent = `of ${pm.all.length} orderings`;
    verdict.className = "verdict wait";
    const left = stops.length - seq.length;
    verdict.textContent = `Tap ${left} more stop${left === 1 ? "" : "s"} · energy so far ${fmt(ev.e)}`;
  }
  // gauge
  const gmax = Math.max(battery * 1.5, pm.maxE * 0.55, ev.e);
  const gi = document.getElementById("gauge-i");
  gi.style.width = (seq.length ? (ev.e / gmax) * 100 : 0) + "%";
  gi.classList.toggle("over", ev.e > battery + 1e-9);
  document.getElementById("gauge-b").style.left = (battery / gmax) * 100 + "%";
  document.getElementById("gauge-l").textContent = `battery ${fmt(battery)} at the mark`;
  // legs
  const legsEl = document.getElementById("legs");
  legsEl.innerHTML = ev.legs.map(l => {
    const a = (l.ea / pm.maxLeg) * 100, b = (l.eb / pm.maxLeg) * 100;
    const nm = n => (n ? n : "H");
    return `<div class="legrow"><span class="lbl"><b>${nm(l.from)} → ${nm(l.to)}</b> ${fmt(l.w, 1)} kg</span>
      <span class="bar"><span class="a" style="width:${a}%"></span><span class="b" style="width:${b}%"></span></span>
      <span class="ev">${fmt(l.e)}</span></div>`;
  }).join("");
  drawRug(ev);
  // callout
  const feasible = pm.all.filter(a => a.e <= battery + 1e-9).length;
  const sh = pm.shortest, sol = evaluate(stops, stops);
  const shortSame = sh.s.join() === stops.join();
  let txt = `${feasible} of the ${pm.all.length} ways to fly drone ${cur + 1}'s stops fit within its battery. `;
  if (shortSame) txt += `Here the shortest ordering, ${fmt(sh.d)} km, is also the cheapest: the heavy parcels already sit near the front. Reversing it costs ${fmt(evaluate(stops.slice().reverse(), stops).e - sol.e)} more energy over the same ${fmt(sol.d)} km.`;
  else txt += `The shortest ordering is ${fmt(sh.d)} km against the solver's ${fmt(sol.d)} km, yet it needs ${fmt(sh.e)} energy to the solver's ${fmt(sol.e)}${sh.e > battery ? `, ${Math.round(sh.e / battery * 100)}% of the battery. The shorter flight would never make it home` : ""}.`;
  document.getElementById("callout").textContent = txt;
}
function drawRug(ev) {
  const svg = document.getElementById("rug");
  const pm = PERMS[cur], stops = ROUTES[cur];
  const W = svg.getBoundingClientRect().width || 500, Hh = 92;
  svg.setAttribute("viewBox", `0 0 ${W} ${Hh}`);
  svg.innerHTML = "";
  const max = Math.max(pm.maxE, battery) * 1.04, min = 0;
  const x = v => 8 + (W - 16) * (v - min) / (max - min);
  const base = 58;
  el("rect", { x: x(battery), y: 14, width: Math.max(0, x(max) - x(battery)), height: base - 14, fill: "var(--caution)", "fill-opacity": 0.06 }, svg);
  el("line", { x1: 8, x2: W - 8, y1: base, y2: base, stroke: "var(--ink)", "stroke-width": 1 }, svg);
  const step = max > 30 ? 10 : max > 12 ? 5 : max > 5 ? 2 : 1;
  for (let v = 0; v <= max; v += step) {
    el("line", { x1: x(v), x2: x(v), y1: base, y2: base + 4, stroke: "var(--ink)" }, svg);
    el("text", { x: x(v), y: base + 16, "text-anchor": "middle" }, svg).textContent = v;
  }
  const op = pm.all.length > 100 ? 0.25 : 0.6;
  pm.all.forEach(a => el("line", { x1: x(a.e), x2: x(a.e), y1: base - 22, y2: base, stroke: "var(--muted)", "stroke-opacity": op, "stroke-width": 1 }, svg));
  el("line", { x1: x(battery), x2: x(battery), y1: 8, y2: base, stroke: "var(--caution)", "stroke-width": 1.5, "stroke-dasharray": "3 2" }, svg);
  if (x(max) - x(battery) > 90) el("text", { x: W - 12, y: 28, "text-anchor": "end", style: "fill:var(--caution)" }, svg).textContent = "over battery";
  const sol = evaluate(stops, stops).e;
  el("path", { d: `M${x(sol)} ${base + 20} l-4 7 h8 z`, fill: "var(--accent)" }, svg);
  el("text", { x: x(sol), y: base + 37, "text-anchor": "middle", style: "fill:var(--accent)" }, svg).textContent = "solver";
  if (ev.complete) {
    el("line", { x1: x(ev.e), x2: x(ev.e), y1: base - 36, y2: base, stroke: COLORS[cur], "stroke-width": 3 }, svg);
    const anchor = x(ev.e) > W - 60 ? "end" : x(ev.e) < 60 ? "start" : "middle";
    el("text", { x: x(ev.e), y: base - 40, "text-anchor": anchor, style: "fill:var(--ink)" }, svg).textContent = "your order";
  }
  document.getElementById("rug-title").textContent = `Energy of all ${pm.all.length} orderings of these ${stops.length} stops`;
}
new ResizeObserver(() => { if (ROUTES[cur]) drawRug(evaluate(seq, ROUTES[cur])); }).observe(document.querySelector(".rug-box"));
selectRoute(3);
tabs.addEventListener("keydown", e => {
  if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
  const n = (cur + (e.key === "ArrowRight" ? 1 : ROUTES.length - 1)) % ROUTES.length;
  selectRoute(n, true); document.getElementById("tab-" + n).focus();
});
