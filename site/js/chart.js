// The hero chart: OSM basemap, restricted zone, the five routes and their playback.
/* ---------- hero chart ---------- */
const map = document.getElementById("map");
(function buildMap() {
  const defs = el("defs", {}, map);
  const lg = el("linearGradient", { id: "bmfade", gradientUnits: "userSpaceOnUse", x1: 0, y1: BM.bounds_top_y - 40, x2: 0, y2: BM.bounds_top_y + 90 }, defs);
  el("stop", { offset: 0, "stop-color": "#000" }, lg);
  el("stop", { offset: 1, "stop-color": "#fff" }, lg);
  const mask = el("mask", { id: "bmmask", maskUnits: "userSpaceOnUse", x: 0, y: 0, width: 1000, height: H }, defs);
  el("rect", { x: 0, y: 0, width: 1000, height: H, fill: "url(#bmfade)" }, mask);
  const cp = el("clipPath", { id: "nfclip" }, defs);
  el("path", { d: nfPath }, cp);

  const bm = el("g", { id: "basemap", mask: "url(#bmmask)" }, map);
  [["green", "bm-green"], ["built", "bm-built"], ["watera", "bm-watera"], ["waterl", "bm-waterl"], ["street", "bm-street"], ["secondary", "bm-secondary"], ["arterial", "bm-arterial"]]
    .forEach(([k, c]) => el("path", { d: BM[k], class: c }, bm));

  // graticule: whole arc-minutes; at the equator a minute of longitude is as long as a minute of latitude
  const grat = el("g", {}, map);
  for (let m = 1; m <= 5; m++) {
    const y = (LAT0 + m / 60) * S;
    if (y < 30 || y > H - 30) continue;
    el("line", { x1: 0, x2: 1000, y1: y, y2: y, class: "grat" }, grat);
    el("line", { x1: 0, x2: 14, y1: y, y2: y, class: "grat-tick" }, grat);
    const t = scaled(grat, 6, y);
    el("text", { x: 14, y: -4, class: "grat-label" }, t).textContent = `0°0${m}′S`;
  }
  for (const m of [18, 19, 20, 21]) {
    const x = (109 + m / 60 - LON0) * S;
    if (x < 30 || x > 940) continue;
    el("line", { x1: x, x2: x, y1: 0, y2: H, class: "grat" }, grat);
    el("line", { x1: x, x2: x, y1: H - 14, y2: H, class: "grat-tick" }, grat);
    const t = scaled(grat, x, H - 6);
    el("text", { x: 5, y: -4, class: "grat-label" }, t).textContent = `109°${m}′E`;
  }
  // the equator runs just north of this sheet
  const et = scaled(map, 0, 0);
  el("path", { d: "M18 26 L18 8 M13 13 L18 8 L23 13", class: "grat-tick", fill: "none" }, et);
  el("text", { x: 30, y: 20, class: "equator-label" }, et).textContent = `EQUATOR  ${fmt(-LAT0 * 111.195, 1)} KM NORTH`;

  // places, kept clear of the delivery area and the restricted zone
  const stopPts = Object.values(P), placed = [];
  BM.places.forEach(p => {
    if (p.y < 70 || p.y > H - 50 || p.x < 80 || p.x > 920 || (p.x > 620 && p.y < 230)) return;
    if (placed.some(q => Math.abs(q[0] - p.x) < 170 && Math.abs(q[1] - p.y) < 40)) return;
    placed.push([p.x, p.y]);
    if (stopPts.some(q => Math.hypot(q[0] - p.x, q[1] - p.y) < 70)) return;
    if (p.x > nfBox.x0 - 60 && p.x < nfBox.x1 + 60 && p.y > nfBox.y0 - 30 && p.y < nfBox.y1 + 30) return;
    const g = scaled(map, p.x, p.y);
    el("text", { "text-anchor": "middle", class: "place" + (p.k === "city" ? " city" : "") }, g).textContent = p.n.toUpperCase();
  });

  // restricted airspace, drawn the way charts draw it: a line with hatching on the inside
  const nf = el("g", {}, map);
  el("path", { d: nfPath, class: "nf-fill" }, nf);
  el("path", { d: nfPath, class: "nf-hatch", "clip-path": "url(#nfclip)" }, nf);
  el("path", { d: nfPath, class: "nf-line" }, nf);
  const nl = scaled(nf, (nfBox.x0 + nfBox.x1) / 2, nfBox.y1);
  el("text", { "text-anchor": "middle", y: 15, class: "nf-label" }, nl).textContent = "RESTRICTED";
  el("text", { "text-anchor": "middle", y: 26, class: "nf-label", style: "font-weight:400" }, nl).textContent = "PONTIANAK CITY · R 0.8 KM";

  // scale bar and north arrow in the open band under the equator
  const km = (1 / 111.19493) * S, sx = 1000 - 40 - km;
  const bar = el("g", { class: "scalebar" }, map);
  el("rect", { x: sx, y: 88, width: km / 2, height: 5, fill: "var(--ink)" }, bar);
  el("rect", { x: sx + km / 2, y: 88, width: km / 2, height: 5, fill: "var(--panel)" }, bar);
  el("text", {}, scaled(bar, sx, 82)).textContent = "0";
  el("text", { "text-anchor": "end" }, scaled(bar, sx + km, 82)).textContent = "1 KM";
  const north = scaled(map, 950, 150, "north");
  el("path", { d: "M0 -16 L6 6 L0 2 L-6 6 Z" }, north);
  el("text", { "text-anchor": "middle", y: 20 }, north).textContent = "N";
})();

const routesG = el("g", { class: "routes" }, map);
const flownG = el("g", { class: "flown" }, map);
const stopsG = el("g", {}, map);
const dronesG = el("g", {}, map);
const plan = ROUTES.map((stops, r) => {
  const ev = evaluate(stops, stops);
  const g = el("g", { class: "route" }, routesG);
  const gf = el("g", { class: "route-f" }, flownG);
  const lines = ev.legs.map(l => {
    const [x1, y1] = P[l.from], [x2, y2] = P[l.to];
    const attrs = { x1, y1, x2, y2, class: "leg" + (l.w > 1e-6 ? "" : " empty"), stroke: COLORS[r], "stroke-width": legWidth(l.w) };
    el("line", attrs, g);
    const f = el("line", { ...attrs, x2: x1, y2: y1 }, gf);
    return f;
  });
  return { r, stops, ev, g, gf, lines };
});
const stopEls = {};
D.customers.forEach(c => {
  const [x, y] = P[c.id];
  const g = scaled(stopsG, x, y, "stop");
  el("circle", { r: 4.6, class: "dot" }, g);
  el("text", { x: 7, y: -6 }, g).textContent = c.id;
  stopEls[c.id] = g;
});
plan.forEach(p => p.stops.forEach(c => stopEls[c].dataset.route = p.r));
(function depot() {
  const g = scaled(stopsG, P[0][0], P[0][1], "depot");
  el("circle", { r: 13, class: "ring" }, g);
  el("circle", { r: 9.5 }, g);
  el("text", { "text-anchor": "middle", y: 4 }, g).textContent = "H";
})();
plan.forEach(p => {
  const g = scaled(dronesG, P[0][0], P[0][1], "drone");
  [[-6, -6, 6, 6], [-6, 6, 6, -6]].forEach(([a, b, c, d]) => el("line", { x1: a, y1: b, x2: c, y2: d, class: "arm" }, g));
  [[-6, -6], [6, -6], [-6, 6], [6, 6]].forEach(([x, y]) => el("circle", { cx: x, cy: y, r: 3.3, class: "rotor", stroke: COLORS[p.r] }, g));
  el("rect", { x: -3.2, y: -3.2, width: 6.4, height: 6.4, class: "hub", fill: COLORS[p.r] }, g);
  g.style.display = "none";
  p.drone = g;
});

/* manifest */
const manifest = document.getElementById("manifest");
plan.forEach(p => {
  const row = document.createElement("div");
  row.className = "mrow";
  row.innerHTML = `<span class="sw" style="border-color:${COLORS[p.r]}"></span>
    <span class="who"><b>Drone ${p.r + 1}</b><span>${p.stops.join(" → ")}</span></span>
    <span class="kg"></span>
    <span class="bat"><span class="track"><i style="background:${COLORS[p.r]}"></i></span><span class="bv"></span></span>`;
  manifest.appendChild(row);
  p.row = row;
  p.kgEl = row.querySelector(".kg"); p.barEl = row.querySelector(".track i"); p.bvEl = row.querySelector(".bv");
  p.payload = p.stops.reduce((s, c) => s + dem[c], 0);
  row.addEventListener("mouseenter", () => focusRoute(p.r));
  row.addEventListener("mouseleave", () => focusRoute(null));
});
function focusRoute(r) {
  map.classList.toggle("focus-on", r !== null);
  plan.forEach(p => {
    const on = p.r === r;
    p.g.classList.toggle("is-focus", on); p.gf.classList.toggle("is-focus", on); p.row.classList.toggle("is-focus", on);
  });
}
function setManifest(p, onboard, used) {
  p.kgEl.textContent = fmt(onboard, 2) + " kg";
  p.barEl.style.width = Math.min(100, (used / battery) * 100) + "%";
  p.bvEl.textContent = `${fmt(used)} · ${Math.round((used / battery) * 100)}%`;
}
document.getElementById("total-e").textContent = fmt(plan.reduce((s, p) => s + p.ev.e, 0));

/* map rescale */
function scaleMap() {
  const w = map.getBoundingClientRect().width || 600;
  const k = 1000 / w;
  rescale(map, k);
}
new ResizeObserver(scaleMap).observe(map);
scaleMap();

/* playback: every drone at one speed, a short hover at each stop */
const SPEED = 0.62, HOVER = 0.35;
plan.forEach(p => {
  let t = 0;
  p.timeline = p.ev.legs.map((l, i) => {
    const seg = { i, t0: t, t1: t + l.d / SPEED, l };
    t = seg.t1 + (l.to ? HOVER : 0);
    return seg;
  });
  p.T = t;
});
const TOTAL = Math.max(...plan.map(p => p.T)) + 0.4;
let playing = false, t0 = 0, tNow = 0, raf = 0;
const playBtn = document.getElementById("play");
function restState() {
  routesG.classList.remove("dim");
  plan.forEach(p => {
    p.drone.style.display = "none";
    p.lines.forEach(f => { f.setAttribute("x2", f.getAttribute("x1")); f.setAttribute("y2", f.getAttribute("y1")); });
    p.stops.forEach(c => { stopEls[c].classList.add("done"); stopEls[c].querySelector(".dot").style.fill = COLORS[p.r]; });
    setManifest(p, p.payload, p.ev.e);
  });
}
function frame(t) {
  plan.forEach(p => {
    let onboard = p.payload, used = 0, pos = P[0];
    p.timeline.forEach(seg => {
      const f = seg.l, line = p.lines[seg.i];
      const [x1, y1] = P[f.from], [x2, y2] = P[f.to];
      let frac = t <= seg.t0 ? 0 : t >= seg.t1 ? 1 : (t - seg.t0) / (seg.t1 - seg.t0);
      const x = x1 + (x2 - x1) * frac, y = y1 + (y2 - y1) * frac;
      line.setAttribute("x2", x); line.setAttribute("y2", y);
      if (t > seg.t0) { pos = [x, y]; used += f.e * frac; }
      if (f.to) {
        const done = t >= seg.t1;
        stopEls[f.to].classList.toggle("done", done);
        stopEls[f.to].querySelector(".dot").style.fill = done ? COLORS[p.r] : "";
        if (done) onboard -= dem[f.to];
      }
    });
    const home = t >= p.T;
    p.drone.style.display = home ? "none" : "";
    p.drone.dataset.x = pos[0]; p.drone.dataset.y = pos[1];
    setManifest(p, Math.max(0, onboard), used);
  });
  rescale(dronesG, 1000 / (map.getBoundingClientRect().width || 600));
}
function tick(now) {
  if (!playing) return;
  tNow = (now - t0) / 1000;
  if (tNow >= TOTAL) { stop(true); return; }
  frame(tNow);
  raf = requestAnimationFrame(tick);
}
function play() {
  if (tNow >= TOTAL || tNow === 0) tNow = 0;
  routesG.classList.add("dim");
  playing = true; t0 = performance.now() - tNow * 1000;
  playBtn.textContent = "Pause";
  raf = requestAnimationFrame(tick);
}
function stop(finished) {
  playing = false; cancelAnimationFrame(raf);
  if (finished) { tNow = 0; restState(); playBtn.textContent = "Fly again"; }
  else playBtn.textContent = "Resume";
}
playBtn.addEventListener("click", () => (playing ? stop(false) : play()));
restState();
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
if (!reduce) setTimeout(() => { if (!playing && tNow === 0) play(); }, 900);
