"""V6.4 P3-1 / P2 -- INDEPENDENT geometric penetration check (plan 7.3).

WHY THIS EXISTS AND WHY cp[8] WAS WRONG
---------------------------------------
The first comparison run (`p2_compare.py`) printed "FAIL(>1mm)" for every candidate by reading `cp[8]` from the
contact cache. Plan 7.3 is explicit that this is not admissible:

    "穿透门禁必须用独立几何校验（validate_geometry.py），不得以 cp[8] 作为结论"

`cp[8]` is the solver's contact separation, reported for pairs the solver chose to keep in its cache, and it is
`-0.00432` for the (R, A) pair at t=0.451 s in EVERY run including the untouched baseline -- i.e. it is the transient
overlap of a 0.145 kg ball striking a 1.5 kg radio at 7 m/s, which is a property of the impact and not of the layout
under test. Using it as the gate would have declared the author's own baseline illegal and, worse, would have made
every candidate look equally bad, hiding the real differences.

WHAT THIS MEASURES INSTEAD
--------------------------
`p.getClosestPoints(a, b, distance)` is a GEOMETRIC query: it computes the true closest points between two bodies'
collision geometries. It does not read the contact cache, does not depend on which pairs the solver retained, and is
therefore independent of the solver's own contact report. For every tracked pair, on a fixed cadence, this records
the minimum separation and the worst pair. Positive separation means a gap; negative means the geometries actually
overlap.

For the oriented boxes the answer is exact. For the radio (a 37-part compound) and the ball (a convex hull) the query
uses the same collision meshes the solver uses, so it reports the same geometry the solver sees rather than an
approximation of it.

The gate is the plan's: **penetration must not exceed 1 mm** for resting contacts. Transient impact overlap is
reported SEPARATELY and explicitly, because conflating a 4 ms impact overlap with a resting 4 cm interpenetration is
exactly the mistake this script exists to prevent -- in the facing rebuild, F41/F42 were overlapping by 3.99 cm at
t=0.001 s, which is a real resting interpenetration and not an impact transient.

This is diagnostic only: it changes nothing in the world.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np

sys.path.insert(0, "/data/raw/huzijian/project1_database/tools/v64")
import physics_common_r10 as pc

ap = argparse.ArgumentParser()
ap.add_argument("--layout", default="")
ap.add_argument("--label", default="baseline")
ap.add_argument("--hz", type=int, default=960)
ap.add_argument("--sim-s", type=float, default=4.0)
ap.add_argument("--ext", type=float, default=0.0)
ap.add_argument("--every", type=int, default=8, help="check the geometry every N substeps")
ap.add_argument("--query-dist", type=float, default=0.02,
                help="only report pairs closer than this distance")
args = ap.parse_args()

OUT = pc.ROOT / "outcomes/v64/radio_scurve_domino/v64_20261006_p0/p2"
OUT.mkdir(parents=True, exist_ok=True)

print("=" * 100, flush=True)
print(f"V6.4 independent geometric penetration check -- {args.label}", flush=True)
print("=" * 100, flush=True)

t0 = time.time()
w = pc.World(hz=args.hz, mode="upstream", verbose=False, layout_override=(args.layout or None))
w.set_initial_state(extend_flight_s=args.ext)

ids = list(w.actors)
bodies = {i: w.actors[i] for i in ids}
# the pairs whose geometry matters: the chain plus the desktop actors. Built from the settled neighbour structure
# rather than from the contact log, so the check does not inherit the solver's idea of what is touching.
pairs = set()
ground = [r["id"] for r in w.layout["objects"]]
for i in range(len(ground) - 1):
    pairs.add((ground[i], ground[i + 1]))
    if i + 2 < len(ground):
        pairs.add((ground[i], ground[i + 2]))
for a in ("B", "A", "R"):
    for b in ("B", "A", "R", *ground[:8]):
        if a != b:
            pairs.add((a, b))
pairs = sorted(pairs)
print(f"  checking {len(pairs)} pairs geometrically every {args.every} substeps, "
      f"reporting pairs closer than {args.query_dist} m", flush=True)

steps = int(args.sim_s * args.hz)
worst = None
worst_resting = None
samples = []
nframes = 0
for s in range(steps):
    pc.p.stepSimulation(physicsClientId=w.cid)
    t = (s + 1) / args.hz
    if s % args.every:
        continue
    nframes += 1
    for (na, nb) in pairs:
        pts = pc.p.getClosestPoints(bodies[na], bodies[nb], args.query_dist, physicsClientId=w.cid)
        if not pts:
            continue
        d = min(pt[8] for pt in pts)
        rec = {"t": round(t, 5), "pair": [na, nb], "separation": d}
        if worst is None or d < worst["separation"]:
            worst = rec
        # a RESTING overlap is one that persists: an impact transient is over within a few substeps. Classify by
        # whether this pair is ALSO overlapping at a much later time, which cannot be an impact transient.
        samples.append(rec)

# the persistent-vs-transient split: for each pair, how many sampled frames show overlap, and over what span?
from collections import defaultdict
by_pair = defaultdict(list)
for r in samples:
    if r["separation"] < 0:
        by_pair[tuple(r["pair"])].append(r)
persistent = {}
for pair, rs in by_pair.items():
    span = rs[-1]["t"] - rs[0]["t"]
    persistent["--".join(pair)] = {
        "min_separation": round(min(x["separation"] for x in rs), 6),
        "first_t": rs[0]["t"], "last_t": rs[-1]["t"], "span_s": round(span, 5),
        "n_overlapping_frames": len(rs),
        "classification": "PERSISTENT (resting interpenetration)" if span > 0.05 else "transient (impact overlap)",
    }
for k, v in sorted(persistent.items(), key=lambda kv: kv[1]["min_separation"]):
    flag = "FAIL" if (v["classification"].startswith("PERSISTENT") and v["min_separation"] < -0.001) else "ok"
    print(f"  {k:<14} min {v['min_separation']:+.6f} m  span {v['span_s']:.4f} s  "
          f"{v['n_overlapping_frames']} frames  {v['classification']}  [{flag}]", flush=True)

if worst:
    print(f"\n  worst geometric separation: {worst['separation']:+.6f} m on {worst['pair']} at t={worst['t']}",
          flush=True)
print(f"  sampled frames {nframes}, wall {time.time() - t0:.1f} s", flush=True)

persistent_failures = {k: v for k, v in persistent.items()
                       if v["classification"].startswith("PERSISTENT") and v["min_separation"] < -0.001}
verdict = "PASS" if not persistent_failures else "FAIL"
print(f"\n  GATE (plan 7.3, resting penetration <= 1 mm): {verdict}", flush=True)
if persistent_failures:
    for k, v in persistent_failures.items():
        print(f"    {k}: {v['min_separation']:+.6f} m over {v['span_s']:.4f} s", flush=True)

report = {
    "status": "P3_1_INDEPENDENT_GEOMETRY",
    "method": ("p.getClosestPoints, a GEOMETRIC query, rather than cp[8] from the contact cache. Plan 7.3 forbids "
               "using cp[8] as the penetration conclusion; the first comparison run did exactly that and declared "
               "every candidate illegal on a -4.32 mm (R,A) impact transient that the untouched baseline also has"),
    "label": args.label, "layout": args.layout or "settled", "hz": args.hz, "sim_s": args.sim_s,
    "pairs_checked": len(pairs), "sample_every": args.every, "sampled_frames": nframes,
    "worst": worst,
    "overlaps": persistent,
    "persistent_failures": persistent_failures,
    "gate": verdict,
    "gate_threshold_m": -0.001,
}
(OUT / f"geometry_{args.label}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {OUT / f'geometry_{args.label}.json'}", flush=True)
w.close()
