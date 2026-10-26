// Shared model: projection, haversine distance and the energy function e(d, w) = d·(α + βw),
// plus the small SVG helpers every view uses. Reads D (data/instance.js) and BM (data/basemap.js).
/* ---------- model ---------- */
const LON0 = 109.296, LAT0 = -0.024, S = 1000 / 0.054, H = BM.H;
const proj = (lat, lon) => [(lon - LON0) * S, (LAT0 - lat) * S];
const RK = 6371.0088, rad = x => x * Math.PI / 180;
const coord = { 0: D.depot }, dem = { 0: 0 };
D.customers.forEach(c => { coord[c.id] = [c.coord[0], c.coord[1]]; dem[c.id] = c.demand; });
const P = {}; Object.keys(coord).forEach(k => P[k] = proj(coord[k][0], coord[k][1]));
const _dc = {};
function dist(a, b) {
  const key = a < b ? a + "-" + b : b + "-" + a;
  if (_dc[key] !== undefined) return _dc[key];
  const [la1, lo1] = coord[a].map(rad), [la2, lo2] = coord[b].map(rad);
  const x = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2;
  return (_dc[key] = 2 * RK * Math.asin(Math.min(1, Math.sqrt(x))));
}
const { alpha, beta, battery } = D;
function evaluate(seq, stops) {
  let w = stops.reduce((s, c) => s + dem[c], 0), prev = 0, e = 0, d = 0;
  const legs = [];
  const complete = seq.length === stops.length;
  const path = complete ? [...seq, 0] : seq;
  for (const c of path) {
    const dd = dist(prev, c), ea = alpha * dd, eb = beta * Math.max(w, 0) * dd;
    legs.push({ from: prev, to: c, d: dd, w: Math.max(w, 0), ea, eb, e: ea + eb });
    e += ea + eb; d += dd;
    if (c) w -= dem[c];
    prev = c;
  }
  return { legs, e, d, complete };
}
function permutations(a) {
  if (a.length <= 1) return [a.slice()];
  const out = [];
  a.forEach((x, i) => permutations([...a.slice(0, i), ...a.slice(i + 1)]).forEach(p => out.push([x, ...p])));
  return out;
}
const ROUTES = D.routes;
const COLORS = ["--r1", "--r2", "--r3", "--r4", "--r5"].map(v => `var(${v})`);
const fmt = (x, n = 2) => x.toFixed(n);

/* ---------- svg helpers ---------- */
const NS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}
function scaled(parent, x, y, cls) {
  const g = el("g", cls ? { class: cls } : {}, parent);
  g.dataset.x = x; g.dataset.y = y;
  return g;
}
function rescale(svg, k) {
  svg.querySelectorAll("g[data-x]").forEach(g => g.setAttribute("transform", `translate(${g.dataset.x} ${g.dataset.y}) scale(${k})`));
}
const nfPath = "M" + D.nofly.map(p => proj(p[0], p[1]).map(v => v.toFixed(1)).join(" ")).join("L") + "Z";
const nfPts = D.nofly.map(p => proj(p[0], p[1]));
const nfBox = { x0: Math.min(...nfPts.map(p => p[0])), x1: Math.max(...nfPts.map(p => p[0])), y0: Math.min(...nfPts.map(p => p[1])), y1: Math.max(...nfPts.map(p => p[1])) };
const legWidth = w => (w > 1e-6 ? 1.3 + 0.95 * w : 1.3);
