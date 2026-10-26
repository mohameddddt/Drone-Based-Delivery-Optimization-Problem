// Flight strips, the Split tour, the confidence-interval chart and the copy buttons.
/* ---------- flight strips ---------- */
const METHODS = [
  { code: "ALNS", tag: "alns", name: "Adaptive large neighbourhood search", idea: "Four destroy and three repair operators chosen by adaptive weights, with energy-aware insertion and noise.", e: 1002.7, t: 24.96, opt: "5/5", best: true },
  { code: "SA", tag: "sa", name: "Simulated annealing", idea: "Same giant-tour encoding. 2-opt, swap and or-move moves, geometric cooling scheduled on the clock.", e: 1002.7, t: 25.0, opt: "5/5", best: true },
  { code: "GA", tag: "ga", name: "Genetic algorithm", idea: "Giant tour plus Split. Tournament selection, order crossover, swap and 2-opt mutation, elitism.", e: 1015.3, t: 21.16, opt: "5/5" },
  { code: "B&B", tag: "bnb", name: "Branch & Bound", idea: "Depth-first over partitions into ordered routes, symmetry-broken, with an anytime lower bound.", e: 1191.7, t: 12.08, opt: "5/5" },
  { code: "GRD", tag: "greedy", name: "Greedy construction", idea: "Nearest-neighbour and Clarke–Wright savings, both constraint-aware. The cheaper is kept and warm-starts the rest.", e: 1232.1, t: 0.0, opt: "0/5" },
];
const strips = document.getElementById("strips");
const emax = 1232.1;
METHODS.forEach(m => {
  const s = document.createElement("div");
  s.className = "strip";
  s.innerHTML = `<div class="code">${m.code}<small>${m.tag}</small></div>
    <div class="what"><h3>${m.name}${m.best ? '<span class="chip">Best avg. energy</span>' : ""}</h3><p>${m.idea}</p></div>
    <div class="cell"><span class="label">Avg. energy</span><span class="v">${m.e.toFixed(1)}</span></div>
    <div class="cell"><span class="label">Avg. time</span><span class="v">${m.t.toFixed(2)} s</span></div>
    <div class="cell"><span class="label">Optima</span><span class="v">${m.opt}</span></div>
    <div class="ebar"><span class="label" style="display:block">0 → ${emax.toFixed(0)}</span><span class="t"><i class="${m.best ? "best" : ""}" style="width:${(m.e / emax) * 100}%"></i></span></div>`;
  strips.appendChild(s);
});

/* split tour */
const tour = document.getElementById("tour");
ROUTES.forEach((r, i) => {
  if (i) { const c = document.createElement("span"); c.className = "cut"; c.setAttribute("aria-hidden", "true"); tour.appendChild(c); }
  const seg = document.createElement("div"); seg.className = "seg";
  seg.innerHTML = `<div class="cells">${r.map(c => `<span style="border-bottom-color:${COLORS[i]}">${c}</span>`).join("")}</div><span class="label">Drone ${i + 1} · ${fmt(evaluate(r, r).e)}</span>`;
  tour.appendChild(seg);
});

/* ---------- CI chart ---------- */
(function ci() {
  const svg = document.getElementById("ci");
  const rows = [["SA", 0.5058, 0.1045, 1.0759], ["ALNS", 0.9249, 0.3652, 1.5472], ["GA", 1.4376, 0.2572, 3.248], ["B&B", 13.0919, 5.2517, 21.2635], ["Greedy", 19.9923, 14.1101, 25.8569]];
  const x0 = 70, x1 = 500, max = 30, x = v => x0 + (x1 - x0) * v / max;
  rows.forEach(([m, mean, lo, hi], i) => {
    const y = 26 + i * 40;
    el("line", { x1: x0, x2: x1, y1: y, y2: y, stroke: "var(--rule-soft)" }, svg);
    el("text", { x: 0, y: y + 4, class: "m" }, svg).textContent = m;
    el("line", { x1: x(lo), x2: x(hi), y1: y, y2: y, stroke: "var(--ink)", "stroke-width": 2 }, svg);
    el("line", { x1: x(lo), x2: x(lo), y1: y - 5, y2: y + 5, stroke: "var(--ink)", "stroke-width": 1.5 }, svg);
    el("line", { x1: x(hi), x2: x(hi), y1: y - 5, y2: y + 5, stroke: "var(--ink)", "stroke-width": 1.5 }, svg);
    el("circle", { cx: x(mean), cy: y, r: 5, fill: i < 3 ? "var(--accent)" : "var(--panel)", stroke: i < 3 ? "var(--accent)" : "var(--ink)", "stroke-width": 1.5 }, svg);
    const tx = x(hi) + 10;
    el("text", { x: tx, y: y + 4 }, svg).textContent = mean.toFixed(2) + "%";
  });
  const ya = 222;
  el("line", { x1: x0, x2: x1, y1: ya, y2: ya, stroke: "var(--ink)" }, svg);
  for (let v = 0; v <= max; v += 5) {
    el("line", { x1: x(v), x2: x(v), y1: ya, y2: ya + 5, stroke: "var(--ink)" }, svg);
    el("text", { x: x(v), y: ya + 19, "text-anchor": "middle" }, svg).textContent = v + "%";
  }
})();

/* ---------- files + copy ---------- */
document.getElementById("files").innerHTML = ROUTES.map((r, i) => `<li><i style="border-color:${COLORS[i]}"></i><span>pontianak-south-20_drone${i + 1}.plan</span><em>${r.length} stops</em></li>`).join("");
const toast = document.getElementById("toast");
let toastT = 0;
function say(msg) { toast.textContent = msg; toast.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => (toast.hidden = true), 1600); }
document.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", () => {
  const src = document.getElementById(b.dataset.copy), text = src.textContent;
  const fallback = () => { const r = document.createRange(); r.selectNodeContents(src); const s = getSelection(); s.removeAllRanges(); s.addRange(r); say("Selected. Press Ctrl+C to copy"); };
  try { navigator.clipboard.writeText(text).then(() => say("Copied"), fallback); } catch (e) { fallback(); }
}));
