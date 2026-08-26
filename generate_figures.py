"""
Generate all figures for report.tex using hardcoded notebook results.
Only runs short GA/SA for convergence and route visualisations.
"""
from __future__ import annotations
import math, random, time, os
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.size": 11, "axes.grid": True, "grid.alpha": 0.3})
os.makedirs("results", exist_ok=True)

# ── Hardcoded results from the notebook run ───────────────────────────────────
results = [
    dict(instance="S1_n5_k2",  n=5,  K=2, greedy_E=567.3,  bnb_E=452.5,  bnb_opt=True,  bnb_nodes=325,    bnb_t=0.00, ga_best=452.5,  ga_mean=452.5,  sa_best=452.5,  sa_mean=452.5),
    dict(instance="S2_n6_k2",  n=6,  K=2, greedy_E=624.8,  bnb_E=592.5,  bnb_opt=True,  bnb_nodes=1923,   bnb_t=0.02, ga_best=592.5,  ga_mean=592.5,  sa_best=592.5,  sa_mean=592.5),
    dict(instance="S3_n7_k2",  n=7,  K=3, greedy_E=639.3,  bnb_E=568.5,  bnb_opt=True,  bnb_nodes=8951,   bnb_t=0.10, ga_best=568.5,  ga_mean=568.5,  sa_best=568.5,  sa_mean=568.5),
    dict(instance="S4_n8_k3",  n=8,  K=3, greedy_E=691.5,  bnb_E=670.5,  bnb_opt=True,  bnb_nodes=45496,  bnb_t=0.55, ga_best=670.5,  ga_mean=670.5,  sa_best=670.5,  sa_mean=670.5),
    dict(instance="S5_n9_k3",  n=9,  K=3, greedy_E=740.3,  bnb_E=593.7,  bnb_opt=True,  bnb_nodes=298386, bnb_t=3.87, ga_best=593.7,  ga_mean=593.7,  sa_best=593.7,  sa_mean=593.7),
    dict(instance="S6_n10_k3", n=10, K=3, greedy_E=925.1,  bnb_E=839.5,  bnb_opt=False, bnb_nodes=1524112,bnb_t=20.0, ga_best=839.5,  ga_mean=839.5,  sa_best=839.5,  sa_mean=840.8),
    dict(instance="M1_n12_k4", n=12, K=4, greedy_E=1035.7, bnb_E=1035.7, bnb_opt=False, bnb_nodes=1338419,bnb_t=20.0, ga_best=922.1,  ga_mean=924.0,  sa_best=922.1,  sa_mean=922.1),
    dict(instance="M2_n15_k4", n=15, K=4, greedy_E=1316.1, bnb_E=1316.1, bnb_opt=False, bnb_nodes=1170220,bnb_t=20.0, ga_best=1011.2, ga_mean=1038.3, sa_best=1011.2, sa_mean=1025.7),
    dict(instance="M3_n18_k5", n=18, K=5, greedy_E=1564.5, bnb_E=1564.5, bnb_opt=False, bnb_nodes=1065489,bnb_t=20.0, ga_best=1292.5, ga_mean=1303.4, sa_best=1461.6, sa_mean=1495.6),
    dict(instance="L1_n20_k5", n=20, K=5, greedy_E=1830.5, bnb_E=1830.5, bnb_opt=False, bnb_nodes=1082457,bnb_t=20.0, ga_best=1428.2, ga_mean=1458.4, sa_best=1660.0, sa_mean=1664.5),
    dict(instance="L2_n25_k6", n=25, K=6, greedy_E=2122.1, bnb_E=2122.1, bnb_opt=False, bnb_nodes=535228, bnb_t=20.0, ga_best=1702.4, ga_mean=1760.1, sa_best=1923.5, sa_mean=1923.5),
    dict(instance="L3_n30_k6", n=30, K=6, greedy_E=2727.7, bnb_E=2727.7, bnb_opt=False, bnb_nodes=886944, bnb_t=20.0, ga_best=2183.8, ga_mean=2257.4, sa_best=2317.1, sa_mean=2354.2),
]

C_GA, C_SA, C_BNB, C_GR = "#2E75B6", "#C0504D", "#4E8542", "#808080"
names = [r["instance"] for r in results]
x = np.arange(len(names)); w = 0.2

# ── fig_comparison.png ───────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 5))
ax.bar(x-1.5*w, [r["greedy_E"] for r in results], w, label="Greedy",         color=C_GR)
ax.bar(x-0.5*w, [r["bnb_E"]    for r in results], w, label="Branch & Bound", color=C_BNB)
ax.bar(x+0.5*w, [r["ga_best"]  for r in results], w, label="GA",             color=C_GA)
ax.bar(x+1.5*w, [r["sa_best"]  for r in results], w, label="SA",             color=C_SA)
ax.set_xticks(x); ax.set_xticklabels(names, rotation=45, ha="right")
ax.set_ylabel("Total energy (best)")
ax.set_title("Best solution energy by method and instance")
ax.legend(); plt.tight_layout()
plt.savefig("results/fig_comparison.png", dpi=150); plt.close()
print("Saved results/fig_comparison.png")

# ── fig_improvement.png ──────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 4.5))
ga_imp = [100*(r["greedy_E"]-r["ga_best"])/r["greedy_E"] for r in results]
sa_imp = [100*(r["greedy_E"]-r["sa_best"])/r["greedy_E"] for r in results]
ax.plot(x, ga_imp, "o-", color=C_GA, label="GA improvement over greedy")
ax.plot(x, sa_imp, "s-", color=C_SA, label="SA improvement over greedy")
for i, r in enumerate(results):
    if r["bnb_opt"]:
        ax.axvspan(i-0.5, i+0.5, color=C_BNB, alpha=0.10)
ax.set_xticks(x); ax.set_xticklabels(names, rotation=45, ha="right")
ax.set_ylabel("% improvement over greedy")
ax.set_title("Metaheuristic improvement over greedy (green band = B&B proved optimum)")
ax.legend(); plt.tight_layout()
plt.savefig("results/fig_improvement.png", dpi=150); plt.close()
print("Saved results/fig_improvement.png")

# ── fig_bnb_scaling.png ──────────────────────────────────────────────────────
solved = [r for r in results if r["bnb_opt"]]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4))
ns_s = [r["n"] for r in solved]
a1.semilogy(ns_s, [r["bnb_nodes"] for r in solved], "o-", color=C_BNB)
a1.set_xlabel("customers n"); a1.set_ylabel("nodes (log)")
a1.set_title("B&B search-tree growth (solved instances)")
a2.semilogy(ns_s, [max(r["bnb_t"], 1e-3) for r in solved], "o-", color=C_BNB)
a2.set_xlabel("customers n"); a2.set_ylabel("time s (log)")
a2.set_title("B&B runtime to proven optimum")
plt.tight_layout()
plt.savefig("results/fig_bnb_scaling.png", dpi=150); plt.close()
print("Saved results/fig_bnb_scaling.png")

# ── Core model (needed for convergence + routes figures) ─────────────────────
EPS = 1e-9

@dataclass
class DRPInstance:
    name: str; n_customers: int; n_drones: int
    coords: np.ndarray; demand: np.ndarray
    battery: float; payload: float
    alpha: float = 1.0; beta: float = 0.3
    nofly_edges: set = field(default_factory=set)
    _dist: Optional[np.ndarray] = field(default=None, repr=False, compare=False)

    @property
    def N(self): return self.n_customers + 1

    @property
    def dist(self):
        if self._dist is None:
            diff = self.coords[:, None, :] - self.coords[None, :, :]
            self._dist = np.sqrt((diff**2).sum(axis=2))
        return self._dist

    def edge_forbidden(self, i, j):
        a, b = (i, j) if i < j else (j, i)
        return (a, b) in self.nofly_edges


@dataclass
class Solution:
    routes: List[List[int]]


def route_energy(inst, route):
    if not route: return 0.0
    d = inst.dist; onboard = sum(inst.demand[c] for c in route)
    e, prev = 0.0, 0
    for c in route:
        if inst.edge_forbidden(prev, c): return math.inf
        e += d[prev, c] * (inst.alpha + inst.beta * onboard)
        onboard -= inst.demand[c]; prev = c
    if inst.edge_forbidden(prev, 0): return math.inf
    return e + d[prev, 0] * (inst.alpha + inst.beta * onboard)


def route_weight(inst, route): return sum(inst.demand[c] for c in route)


def split(inst, tour):
    n = len(tour)
    if n == 0: return Solution([[] for _ in range(inst.n_drones)]), 0.0
    K = inst.n_drones; INF = math.inf
    dp = [[INF]*(K+1) for _ in range(n+1)]
    parent = [[-1]*(K+1) for _ in range(n+1)]
    dp[0][0] = 0.0
    for i in range(n):
        for k in range(K):
            if dp[i][k] == INF: continue
            for j in range(i+1, n+1):
                seg = tour[i:j]
                if route_weight(inst, seg) > inst.payload + EPS: break
                e = route_energy(inst, seg)
                if math.isinf(e): continue
                if e > inst.battery + EPS: break
                if dp[i][k] + e < dp[j][k+1] - 1e-12:
                    dp[j][k+1] = dp[i][k] + e; parent[j][k+1] = i
    best_k, best_e = -1, INF
    for k in range(1, K+1):
        if dp[n][k] < best_e: best_e, best_k = dp[n][k], k
    if best_k == -1: return None, INF
    routes, j, k = [], n, best_k
    while k > 0:
        i = parent[j][k]; routes.append(tour[i:j]); j, k = i, k-1
    routes.reverse()
    while len(routes) < inst.n_drones: routes.append([])
    return Solution(routes), best_e


def _nn_cost(inst):
    d, unv, cur, cost = inst.dist, set(range(1, inst.N)), 0, 0.0
    onboard = inst.demand[1:].sum()
    while unv:
        nxt = min(unv, key=lambda j: d[cur, j])
        cost += d[cur, nxt]*(inst.alpha + inst.beta*onboard)
        onboard -= inst.demand[nxt]; cur = nxt; unv.discard(nxt)
    return cost + d[cur, 0]*inst.alpha


def generate_instance(name, n_customers, n_drones, seed,
                      area=100.0, d_min=1.0, d_max=5.0,
                      alpha=1.0, beta=0.3, payload_factor=1.7,
                      battery_factor=0.9, nofly_fraction=0.0):
    rng = np.random.default_rng(seed)
    coords = rng.uniform(0, area, size=(n_customers+1, 2))
    coords[0] = [area/2, area/2]
    demand = np.zeros(n_customers+1)
    demand[1:] = rng.uniform(d_min, d_max, size=n_customers)
    payload = max(d_max, payload_factor*demand.sum()/n_drones, demand.max())
    inst = DRPInstance(name=name, n_customers=n_customers, n_drones=n_drones,
                       coords=coords, demand=demand, battery=math.inf,
                       payload=payload, alpha=alpha, beta=beta)
    if nofly_fraction > 0:
        d = inst.dist
        edges = [(i, j, d[i, j]) for i in range(1, inst.N) for j in range(i+1, inst.N)]
        edges.sort(key=lambda e: -e[2])
        inst.nofly_edges = set((e[0], e[1]) for e in edges[:int(nofly_fraction*len(edges))])
    nn = _nn_cost(inst)
    per_drone = nn/max(1, inst.n_drones-1) if inst.n_drones > 1 else nn
    inst.battery = battery_factor * max(nn/inst.n_drones, per_drone)
    return inst


def nearest_neighbour_routes(inst):
    d, unv, routes = inst.dist, set(range(1, inst.N)), []
    while unv and len(routes) < inst.n_drones:
        route, cur = [], 0
        while True:
            best_c, best_d = None, math.inf
            for c in sorted(unv):
                if inst.edge_forbidden(cur, c): continue
                trial = route + [c]
                if route_weight(inst, trial) > inst.payload + EPS: continue
                if route_energy(inst, trial) > inst.battery + EPS: continue
                if d[cur, c] < best_d: best_d, best_c = d[cur, c], c
            if best_c is None: break
            route.append(best_c); unv.discard(best_c); cur = best_c
        if not route: break
        routes.append(route)
    while len(routes) < inst.n_drones: routes.append([])
    return Solution(routes)


def order_crossover(p1, p2, rng):
    n = len(p1); a, b = sorted(rng.sample(range(n), 2))
    child = [None]*n; child[a:b+1] = p1[a:b+1]
    fill = [g for g in p2 if g not in set(p1[a:b+1])]; idx = 0
    for i in range(n):
        if child[i] is None: child[i] = fill[idx]; idx += 1
    return child


def solve_ga(inst, pop_size=60, generations=500, xr=0.9, mr=0.3, elite=4,
             seed=0, time_limit=10.0, warm_tour=None):
    rng = random.Random(seed); t0 = time.time()
    customers = list(range(1, inst.N))

    def fit(tour):
        sol, e = split(inst, tour); return e

    pop = [warm_tour[:]] if warm_tour else []
    while len(pop) < pop_size:
        t = customers[:]; rng.shuffle(t); pop.append(t)

    scored = sorted([(fit(t), t) for t in pop], key=lambda x: x[0])
    history = []

    def tourn():
        i, j = rng.randrange(len(scored)), rng.randrange(len(scored))
        return scored[i][1] if scored[i][0] <= scored[j][0] else scored[j][1]

    for _ in range(generations):
        if time.time() - t0 > time_limit: break
        new = [scored[k][1][:] for k in range(elite)]
        while len(new) < pop_size:
            p1 = tourn()
            child = order_crossover(p1, tourn(), rng) if rng.random() < xr else p1[:]
            if rng.random() < mr:
                if rng.random() < 0.5:
                    ii, jj = rng.sample(range(len(child)), 2); child[ii], child[jj] = child[jj], child[ii]
                else:
                    ii, jj = sorted(rng.sample(range(len(child)), 2)); child[ii:jj+1] = reversed(child[ii:jj+1])
            new.append(child)
        scored = sorted([(fit(t), t) for t in new], key=lambda x: x[0])
        history.append(scored[0][0])

    best_e, best_tour = scored[0]
    sol, e = split(inst, best_tour)
    return sol, e, history


def solve_sa(inst, seed=0, max_iter=40000, gamma=0.9995, time_limit=10.0, warm_tour=None):
    rng = random.Random(seed); t0 = time.time()
    customers = list(range(1, inst.N))
    cur = warm_tour[:] if warm_tour else customers[:]
    if not warm_tour: rng.shuffle(cur)
    cur_sol, cur_e = split(inst, cur)
    for _ in range(200):
        if not math.isinf(cur_e): break
        rng.shuffle(cur); cur_sol, cur_e = split(inst, cur)
    best, best_e = cur[:], cur_e
    deltas = []
    for _ in range(60):
        cand = cur[:]
        if len(cand) >= 2:
            ii, jj = rng.sample(range(len(cand)), 2); cand[ii], cand[jj] = cand[jj], cand[ii]
        _, ce = split(inst, cand)
        if not math.isinf(ce): deltas.append(abs(ce - cur_e))
    avg = sum(deltas)/len(deltas) if deltas else 1.0
    T = T0 = -avg/math.log(0.8) if avg > 0 else 1.0
    stag, history = 0, []

    def neighbour(t):
        t = t[:]; n = len(t)
        m = rng.random()
        if m < 0.34 and n >= 2:
            ii, jj = rng.sample(range(n), 2); t[ii], t[jj] = t[jj], t[ii]
        elif m < 0.67 and n >= 2:
            ii, jj = sorted(rng.sample(range(n), 2)); t[ii:jj+1] = reversed(t[ii:jj+1])
        elif n >= 1:
            ii = rng.randrange(n); c = t.pop(ii); t.insert(rng.randrange(len(t)+1), c)
        return t

    for it in range(max_iter):
        if time.time() - t0 > time_limit: break
        cand = neighbour(cur); _, ce = split(inst, cand)
        if math.isinf(ce): continue
        delta = ce - cur_e
        if delta < 0 or rng.random() < math.exp(-delta/max(T, 1e-9)):
            cur, cur_e = cand, ce
            if cur_e < best_e - EPS: best, best_e = cur[:], cur_e; stag = 0
            else: stag += 1
        else: stag += 1
        T *= gamma
        if stag >= 4000: T = T0*0.5; stag = 0; cur, cur_e = best[:], best_e
        if it % 200 == 0: history.append(best_e)

    best_sol, _ = split(inst, best)
    return best_sol, best_e, history


# ── fig_convergence.png ──────────────────────────────────────────────────────
print("Generating convergence figure (GA+SA on n=18, ~20s)...")
inst_c = generate_instance("conv_n18_k5", 18, 5, 109)
ws_c = nearest_neighbour_routes(inst_c)
wt_c = [c for r in ws_c.routes for c in r]
_, _, ga_hist = solve_ga(inst_c, seed=1, time_limit=10, warm_tour=wt_c)
_, _, sa_hist = solve_sa(inst_c, seed=1, time_limit=10, warm_tour=wt_c)
fig, ax = plt.subplots(figsize=(9, 4.5))
ax.plot(np.linspace(0, 1, len(ga_hist)), ga_hist, color=C_GA, label="GA (best per generation)")
ax.plot(np.linspace(0, 1, len(sa_hist)), sa_hist, color=C_SA, label="SA (best so far)")
ax.set_xlabel("normalised search progress"); ax.set_ylabel("best energy")
ax.set_title("Convergence on conv_n18_k5 (n=18, K=5)")
ax.legend(); plt.tight_layout()
plt.savefig("results/fig_convergence.png", dpi=150); plt.close()
print("Saved results/fig_convergence.png")

# ── fig_routes.png ───────────────────────────────────────────────────────────
print("Generating routes figure (GA on n=10, ~5s)...")
inst_r = generate_instance("routes_n10_k3", 10, 3, 106, nofly_fraction=0.1)
ws_r = nearest_neighbour_routes(inst_r)
wt_r = [c for r in ws_r.routes for c in r]
sol_r, e_r, _ = solve_ga(inst_r, seed=1, time_limit=5, warm_tour=wt_r)
co = inst_r.coords
palette = ["#2E75B6", "#C0504D", "#4E8542", "#8064A2", "#F79646", "#4BACC6"]
fig, ax = plt.subplots(figsize=(7, 6.5))
for ri, route in enumerate([r for r in sol_r.routes if r]):
    pts = [0] + route + [0]
    ax.plot([co[p][0] for p in pts], [co[p][1] for p in pts],
            "-o", color=palette[ri % len(palette)], label=f"drone {ri+1}")
ax.plot(co[0][0], co[0][1], "k*", markersize=20, label="depot")
for c in range(1, inst_r.N):
    ax.annotate(str(c), (co[c][0], co[c][1]), fontsize=8,
                textcoords="offset points", xytext=(4, 4))
ax.set_title(f"GA solution — routes_n10_k3 (E={e_r:.0f})")
ax.legend(fontsize=9); plt.tight_layout()
plt.savefig("results/fig_routes.png", dpi=150); plt.close()
print("Saved results/fig_routes.png")

print("\nAll 5 figures saved to results/")
