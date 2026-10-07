"""V6.4 P2-42 -- WHICH pieces does the vegetation block, and by how much?

WHY THIS MEASUREMENT DECIDES THE REPAIR
---------------------------------------
`p2_vegetation_diag.py` settled the mechanism beyond doubt:

    ARM A (production, vegetation collides) : legal 41/48, down 41/48
    ARM B (vegetation collision off, MARKED): legal 48/48, down 48/48

So the chain's mechanism is COMPLETE -- with the vegetation unable to block it, all 48 pieces relay correctly and the
legal chain is full. The vegetation is the only remaining blocker.

The same run also answered the modelling question:

    grass 129 chunks | potted_plant_01_leaves 36 | weed_plants 22 | pebbles 19 | ivy 6 | leaves 5 | stem 3 | pot 2
    = 222 of the 338 collision bodies
    EVERY vegetation chunk has mass 0.0 and NO joints
    lateral friction 0.75, restitution 0.03 on all of them

Mass 0 with no joints means pybullet treats them as infinitely heavy, completely immovable geometry: they cannot bend,
cannot be pushed aside, and cannot move at all. A real grass blade under a falling domino bends with negligible
resistance, so a rigid grass wall is not a faithful model of the scene -- and, as the user observed, the right
consequence is to keep the dominoes OUT of the vegetation rather than to switch its collision off.

WHAT THIS MEASURES
------------------
For every one of the 48 pieces, across the whole production run:

  * the largest contact force it ever has with VEGETATION, and which object that was;
  * the largest contact force it has with NON-vegetation scenery (stones, walls, floor) -- to separate "the grass
    stopped it" from "a wall stopped it";
  * its peak and final tilt, so a stalled piece can be matched to its blocker.

The output is the list of pieces that need to be moved for the chain to stay out of the vegetation, which is what the
re-placement has to fix. This is a measurement; it changes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/data/raw/huzijian/project1_database/tools/v64")
import physics_common_r10 as pc

ap = argparse.ArgumentParser()
ap.add_argument("--layout", default="/data/raw/huzijian/project1_database/tmp/v64_node12/layout_v64_iter_f05f23.json")
ap.add_argument("--hz", type=int, default=1920)
ap.add_argument("--sim-s", type=float, default=9.0)
ap.add_argument("--ext", type=float, default=0.0)
ap.add_argument("--tilt-threshold", type=float, default=60.0)
ap.add_argument("--vegetation", default="grass,leaves,ivy,weed_plants,potted_plant_01_leaves.001,"
                                        "potted_plant_01_pebbles.001,potted_plant_01_stem.001,potted_plant_01_pot.001")
ap.add_argument("--supports", default="Floor_main,BG_floor")
args = ap.parse_args()

OUT = pc.ROOT / "outcomes/v64/radio_scurve_domino/v64_20261006_p0/p2"
OUT.mkdir(parents=True, exist_ok=True)

manifest = json.loads(pc.DEFAULT_MANIFEST.read_text())
layout = json.loads(open(args.layout, encoding="utf-8").read())
order = [r["id"] for r in layout["objects"]]
D = {o: np.array(manifest["objects"][o]["dims_m"], dtype=float) for o in order}
VEG = {v.strip() for v in args.vegetation.split(",") if v.strip()}
SUP = {s.strip() for s in args.supports.split(",") if s.strip()}

print("=" * 108, flush=True)
print("V6.4 P2-42 -- which pieces does the vegetation block?", flush=True)
print(f"  layout {args.layout.split('/')[-1]}   hz {args.hz}   window {args.sim_s} s", flush=True)
print(f"  vegetation objects: {sorted(VEG)}", flush=True)
print("=" * 108, flush=True)

w = pc.World(hz=args.hz, mode="upstream", verbose=False, layout_override=args.layout)
w.set_initial_state(extend_flight_s=args.ext)

NAMES = list(w.actors)
bodies = {n: w.actors[n] for n in NAMES}
name_of = {b: n for n, b in w.actors.items()}
dyn_ids = set(w.actors.values())
ground = [r["id"] for r in w.layout["objects"]]

# per piece: max vegetation force, max non-vegetation static force, and the first vegetation contact
veg_max = defaultdict(float)
veg_obj = {}
veg_first = {}
other_max = defaultdict(float)
other_obj = {}
for o in w._static:
    pass

steps = int(args.sim_s * args.hz)
pos = {n: np.empty((steps + 1, 3)) for n in NAMES}
quat = {n: np.empty((steps + 1, 4)) for n in NAMES}
for n in NAMES:
    _p, _q = pc.p.getBasePositionAndOrientation(bodies[n], physicsClientId=w.cid)
    pos[n][0], quat[n][0] = _p, _q

for s in range(steps):
    pc.p.stepSimulation(physicsClientId=w.cid)
    t = (s + 1) / args.hz
    for n in NAMES:
        _p, _q = pc.p.getBasePositionAndOrientation(bodies[n], physicsClientId=w.cid)
        pos[n][s + 1], quat[n][s + 1] = _p, _q
    for c in pc.p.getContactPoints(physicsClientId=w.cid):
        b1, b2 = c[1], c[2]
        for mine, other in ((b1, b2), (b2, b1)):
            nm = name_of.get(mine)
            if nm is None or nm not in order:
                continue          # only ground-chain pieces
            if other in dyn_ids:
                continue          # relay contact, not scenery
            oname = w.body_names.get(other)
            f = float(c[9])
            if oname in VEG:
                if f > veg_max[nm]:
                    veg_max[nm] = f
                    veg_obj[nm] = oname
                veg_first.setdefault(nm, {"t": round(t, 5), "object": oname, "force_N": round(f, 4)})
            elif oname not in SUP:
                if f > other_max[nm]:
                    other_max[nm] = f
                    other_obj[nm] = oname

w.pos, w.quat = pos, quat
peaks = {o: round(w.peak_tilt_deg(o), 2) for o in ground}
finals = {}
for o in ground:
    R = np.array(pc.p.getMatrixFromQuaternion(list(quat[o][-1]))).reshape(3, 3)
    finals[o] = round(float(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1)))), 2)
w.close()

print(f"\n  {'piece':<6}{'peak':>8}{'final':>8}{'veg_maxN':>10}{'veg_object':<28}{'other_maxN':>11}  other",
      flush=True)
rows = []
for o in order:
    v = veg_max.get(o, 0.0)
    ot = other_max.get(o, 0.0)
    rows.append({"piece": o, "peak": peaks[o], "final": finals[o], "veg_max_N": round(v, 3),
                 "veg_object": veg_obj.get(o), "veg_first": veg_first.get(o),
                 "other_max_N": round(ot, 3), "other_object": other_obj.get(o)})
    tag = "   <== VEGETATION" if v > 1.0 else ""
    print(f"  {o:<6}{peaks[o]:>8.2f}{finals[o]:>8.2f}{v:>10.2f}{str(veg_obj.get(o) or '-'):<28}"
          f"{ot:>11.2f}  {other_obj.get(o) or '-'}{tag}", flush=True)

touched = [r for r in rows if r["veg_max_N"] > 1.0]
stalled = [r for r in rows if r["final"] < args.tilt_threshold]
print(f"\n  pieces with a significant vegetation contact (>1 N): {len(touched)} of {len(rows)}", flush=True)
print(f"    {[r['piece'] for r in touched]}", flush=True)
print(f"  pieces that did NOT reach {args.tilt_threshold} deg: {len(stalled)}", flush=True)
print(f"    {[r['piece'] for r in stalled]}", flush=True)
print(f"\n  of the stalled pieces, which are touching vegetation:", flush=True)
for r in stalled:
    if r["veg_max_N"] > 1.0:
        print(f"    {r['piece']}: final {r['final']:.2f} deg, vegetation {r['veg_max_N']:.2f} N on "
              f"{r['veg_object']}, other scenery {r['other_max_N']:.2f} N", flush=True)
    else:
        print(f"    {r['piece']}: final {r['final']:.2f} deg, NO significant vegetation contact "
              f"(other scenery {r['other_max_N']:.2f} N on {r['other_object']})", flush=True)

by_obj = defaultdict(list)
for r in touched:
    by_obj[r["veg_object"]].append(r["piece"])
print(f"\n  vegetation objects involved, with the pieces they touch:", flush=True)
for k, v in sorted(by_obj.items(), key=lambda kv: -len(kv[1])):
    print(f"    {k}: {len(v)} pieces {v}", flush=True)

tot = sum(r["veg_max_N"] for r in rows)
print(f"\n  total vegetation contact load across the chain: {tot:.1f} N", flush=True)
print(f"  the pieces needing re-placement to leave the vegetation: {[r['piece'] for r in touched]}", flush=True)

json.dump({"layout": args.layout, "hz": args.hz, "sim_s": args.sim_s, "rows": rows,
           "touched": [r["piece"] for r in touched], "stalled": [r["piece"] for r in stalled],
           "by_object": {k: v for k, v in by_obj.items()}},
          open(OUT / "veg_contacts_tailwest_b_v65.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"\nwrote {OUT / 'veg_contacts_tailwest_b_v65.json'}", flush=True)
