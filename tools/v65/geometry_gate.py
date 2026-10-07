"""V6.5 GATE 2 -- independent dynamic geometry / penetration gate over the FULL scene.

WHY THIS REPLACES THE V6.4 SCREENERS
------------------------------------
V6.5 plan section 3 gate 2 requires penetration to be settled by a geometric distance query, not by the contact
cache's `cp[8]`, and it requires the check to cover the WHOLE native scene and the full motion -- not only the
dynamic-dynamic pairs. V6.4 established why `cp[8]` cannot be the conclusion: the A-R impact reads -4.07 mm at
960 Hz and -0.79 mm at 1920 Hz for the SAME layout, so the number is a property of the timestep rather than of the
geometry.

The plan also states the honest limitation of the existing tool, and this script keeps that limitation visible rather
than papering over it:

  * `getClosestPoints` still uses Bullet's collision geometry, so it is not an independent triangle-mesh test;
  * the earlier implementation covered only a subset of dynamic pairs and none of the native scenery.

What this script adds: EVERY dynamic actor against EVERY static body whose AABB is near the ground corridor (floor,
stones, grass, leaves, walls), plus every dynamic-dynamic pair within range, sampled across the real trajectory. Two
numbers are separated deliberately:

  * PERSISTENT embedding -- a separation below the tolerance sustained for longer than `--persist-s`. This is the
    FAIL condition, because a sustained overlap is a geometric contradiction that no timestep excuse explains.
  * TRANSIENT impact -- a single-sample negative reading, reported with its duration and its pair, because a contact
    solver legitimately resolves a small overlap in one or two substeps.

Gate: no PERSISTENT embedding deeper than 1 mm.

The detector is PROVEN ABLE TO FAIL by an injection test: a box is deliberately placed 3 mm inside a static body and
the same measurement is required to report it. A gate that cannot fail is not a gate, and this project has already
produced several measurements with no discriminating power (a profile that priced the call but not the loop; a
clearance test that included the floor and therefore rejected its own starting point; a swept-volume AABB test whose
"intrusion" was just the box's own size).

Nothing is modified in the production scene; injections happen in a separate World built only for the self-test.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/data/raw/huzijian/project1_database/tools/v64")
import physics_common_r10 as pc

ap = argparse.ArgumentParser()
ap.add_argument("--layout", default="/data/raw/huzijian/project1_database/tmp/v64_node12/"
                                    "layout_v65_tailwest_candidate_b.json")
ap.add_argument("--out-dir", required=True)
ap.add_argument("--hz", type=int, default=1920)
ap.add_argument("--sim-s", type=float, default=9.0)
ap.add_argument("--every", type=int, default=24, help="substeps between geometric samples")
ap.add_argument("--persist-s", type=float, default=0.05, help="embedding longer than this is PERSISTENT")
ap.add_argument("--tol", type=float, default=-0.001, help="FAIL if a persistent separation is below this")
ap.add_argument("--reach", type=float, default=0.06)
ap.add_argument("--alt-hz", type=int, default=960, help="timestep-stability cross-check frequency")
ap.add_argument("--skip-alt", action="store_true")
args = ap.parse_args()

from pathlib import Path

OUT = Path(args.out_dir) if args.out_dir.startswith("/") else pc.ROOT / args.out_dir
OUT.mkdir(parents=True, exist_ok=True)

print("=" * 110, flush=True)
print("V6.5 GATE 2 -- dynamic geometry / penetration, whole scene, over the real trajectory", flush=True)
print(f"  layout {args.layout.split('/')[-1]}   {args.hz} Hz   {args.sim_s} s   sample every {args.every} substeps "
      f"({1000 * args.every / args.hz:.2f} ms)", flush=True)
print(f"  PERSISTENT = separation below {1000 * args.tol:.1f} mm sustained longer than {args.persist_s} s", flush=True)
print("=" * 110, flush=True)


def build():
    w = pc.World(hz=args.hz, mode="upstream", verbose=False, layout_override=args.layout)
    w.set_initial_state()
    NAMES = list(w.actors)
    bodies = {n: w.actors[n] for n in NAMES}
    name_of = {b: n for n, b in w.actors.items()}
    dyn_ids = set(w.actors.values())
    return w, NAMES, bodies, name_of, dyn_ids


def statics_near(w, region_xy, pad):
    """Every native static body whose AABB is within `pad` of the region the chain occupies."""
    (x0, x1), (y0, y1) = region_xy
    out = []
    for sb in w._static:
        try:
            lo, hi = pc.p.getAABB(sb, physicsClientId=w.cid)
        except Exception:
            continue
        if lo[0] - pad <= x1 and hi[0] + pad >= x0 and lo[1] - pad <= y1 and hi[1] + pad >= y0:
            out.append(sb)
    return out


def run(w, NAMES, bodies, name_of, dyn_ids, statics, label, tag):
    """Sample geometric separations across the whole solve and classify persistent vs transient."""
    ground = [r["id"] for r in w.layout["objects"]]
    steps = int(round(args.sim_s * args.hz))
    # per-pair history of (t, separation) for samples that were negative
    neg = defaultdict(list)
    worst = {"sep": 1e9, "pair": None, "t": None}
    n_samples = 0
    sample_times = []
    t0 = time.time()
    ns = set(NAMES)
    for s in range(steps):
        pc.p.stepSimulation(physicsClientId=w.cid)
        if s % args.every:
            continue
        t = (s + 1) / args.hz
        sample_times.append(t)
        n_samples += 1
        # dynamic vs near static
        for nm in ns:
            b = bodies[nm]
            for sb in statics:
                pts = pc.p.getClosestPoints(b, sb, args.reach, physicsClientId=w.cid)
                if not pts:
                    continue
                d = min(pt[8] for pt in pts)
                if d < worst["sep"]:
                    worst = {"sep": float(d), "pair": [nm, f"STATIC {w.body_names.get(sb, sb)}"], "t": t}
                if d < 0:
                    neg[(nm, f"STATIC {w.body_names.get(sb, sb)}")].append((t, float(d)))
        # dynamic vs dynamic, all pairs within range (name-ordered so a pair has one key)
        n = len(NAMES)
        for i in range(n):
            for j in range(i + 1, n):
                a, c = NAMES[i], NAMES[j]
                pts = pc.p.getClosestPoints(bodies[a], bodies[c], args.reach, physicsClientId=w.cid)
                if not pts:
                    continue
                d = min(pt[8] for pt in pts)
                if d < worst["sep"]:
                    worst = {"sep": float(d), "pair": [a, c], "t": t}
                if d < 0:
                    neg[(a, c)].append((t, float(d)))
    wall = time.time() - t0

    # classify: a pair is PERSISTENT if its negative samples span more than persist-s
    persistent, transient = [], []
    for pair, hist in neg.items():
        hist.sort()
        # longest run whose total span exceeds the persistence window
        run_t0 = hist[0][0]
        run_min = hist[0][1]
        prev = hist[0][0]
        runs = []
        for (t, d) in hist[1:]:
            if t - prev > 2.0 * args.every / args.hz:
                runs.append((run_t0, prev, run_min))
                run_t0, run_min = t, d
            run_min = min(run_min, d)
            prev = t
        runs.append((run_t0, prev, run_min))
        for (rt0, rt1, rmin) in runs:
            entry = {"pair": list(pair), "span_s": round(rt1 - rt0, 5), "min_sep_m": round(rmin, 6),
                     "t0": round(rt0, 5), "t1": round(rt1, 5)}
            if (rt1 - rt0) > args.persist_s and rmin < args.tol:
                persistent.append(entry)
            elif rmin < 0:
                transient.append(entry)

    persistent.sort(key=lambda e: e["min_sep_m"])
    transient.sort(key=lambda e: e["min_sep_m"])
    print(f"\n  --- {label} ({tag}) ---", flush=True)
    print(f"    geometric samples {n_samples} over {args.sim_s} s   pairs/sample: {len(NAMES)}x{len(statics)} static "
          f"+ {len(NAMES) * (len(NAMES) - 1) // 2} dynamic   wall {wall:.1f} s", flush=True)
    print(f"    worst separation ever: {1000 * worst['sep']:+.4f} mm at t={worst['t']} on {worst['pair']}", flush=True)
    print(f"    pairs with ANY negative sample: {len(neg)}", flush=True)
    print(f"    PERSISTENT (>{args.persist_s} s and < {1000 * args.tol:.1f} mm): {len(persistent)}", flush=True)
    for e in persistent[:15]:
        print(f"      {e['pair'][0]} vs {e['pair'][1]}: {1000 * e['min_sep_m']:+.3f} mm for "
              f"{1000 * e['span_s']:.1f} ms (t {e['t0']}..{e['t1']})", flush=True)
    print(f"    transient single-sample impacts: {len(transient)}", flush=True)
    for e in transient[:10]:
        print(f"      {e['pair'][0]} vs {e['pair'][1]}: {1000 * e['min_sep_m']:+.3f} mm for "
              f"{1000 * e['span_s']:.1f} ms at t {e['t0']}", flush=True)
    return {"label": label, "tag": tag, "hz": args.hz, "samples": n_samples, "wall_s": round(wall, 1),
            "worst": {"sep_m": worst["sep"], "pair": worst["pair"], "t": worst["t"]},
            "n_negative_pairs": len(neg), "persistent": persistent, "transient": transient,
            "gate_pass": len(persistent) == 0}


results = []
w, NAMES, bodies, name_of, dyn_ids = build()
# region covering the whole chain plus the table and the drop
gp = np.array([r["settled_position"] for r in w.layout["objects"]])
region = ((float(gp[:, 0].min()) - 0.6, float(gp[:, 0].max()) + 0.6),
          (float(gp[:, 1].min()) - 0.6, float(gp[:, 1].max()) + 0.6))
statics = statics_near(w, region, 0.2)
from collections import Counter
kinds = Counter(w.body_names.get(s, "?") for s in statics)
print(f"\n  native static bodies in the corridor region: {len(statics)} of {len(w._static)}", flush=True)
print(f"  kinds: {dict(kinds.most_common(15))}", flush=True)
results.append(run(w, NAMES, bodies, name_of, dyn_ids, statics, "production main", f"hz{args.hz}"))
w.close()

if not args.skip_alt:
    w2, N2, b2, no2, d2 = build()
    st2 = statics_near(w2, region, 0.2)
    results.append(run(w2, N2, b2, no2, d2, st2, "timestep stability check", f"hz{args.alt_hz}"))
    w2.close()

# ---- injection self-test: the gate must be able to FAIL ------------------------------
print(f"\n{'=' * 110}", flush=True)
print("  DETECTOR SELF-TEST -- a 3 mm deliberate embedding must be reported as PERSISTENT", flush=True)
w3 = pc.World(hz=args.hz, mode="upstream", verbose=False, layout_override=args.layout)
w3.set_initial_state()
inj_static = None
for sb in w3._static:
    if w3.body_names.get(sb) == "Floor_main":
        inj_static = sb
        break
lo, hi = pc.p.getAABB(inj_static, physicsClientId=w3.cid)
# put B 3 mm inside the floor slab
inside_z = float(hi[2]) - 0.003
b_body = w3.actors["B"]
pc.p.resetBasePositionAndOrientation(b_body, [float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2), inside_z],
                                     [0, 0, 0, 1], physicsClientId=w3.cid)
pc.p.stepSimulation(physicsClientId=w3.cid)
pts = pc.p.getClosestPoints(b_body, inj_static, 0.10, physicsClientId=w3.cid)
inj_sep = min((pt[8] for pt in pts), default=None)
detected = inj_sep is not None and inj_sep < args.tol
print(f"    injected embedding: B placed at z={inside_z:.6f}, floor top z={hi[2]:.6f} -> nominal depth 3.000 mm", flush=True)
print(f"    measured separation: {None if inj_sep is None else round(1000 * inj_sep, 4)} mm", flush=True)
print(f"    -> detector {'DETECTED the injection (gate can fail: GOOD)' if detected else 'MISSED the injection (GATE IS BROKEN)'}",
      flush=True)
w3.close()

gate_pass = all(r["gate_pass"] for r in results) and detected
summary = {"layout": args.layout, "hz": args.hz, "alt_hz": args.alt_hz, "sim_s": args.sim_s,
           "every": args.every, "persist_s": args.persist_s, "tol_m": args.tol,
           "n_static_bodies_checked": len(statics), "static_kinds": dict(kinds),
           "runs": results,
           "self_test": {"injected_depth_m": 0.003, "measured_sep_m": inj_sep, "detected": bool(detected)},
           "gate_pass": bool(gate_pass),
           "limitation": ("getClosestPoints uses Bullet collision geometry, so this is NOT an independent triangle "
                          "test; it does cover the full native scene and the whole motion, which the previous "
                          "screeners did not.")}
(OUT / "geometry_gates.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  GATE 2 VERDICT: {'PASS' if gate_pass else 'FAIL'}", flush=True)
print(f"wrote {OUT / 'geometry_gates.json'}", flush=True)
