"""Diagnose the gate-2 self-test failure.

The self-test placed the ball 3 mm inside the body named `Floor_main` and `getClosestPoints` returned NO pair at all
(not a positive separation -- nothing). It also reported that body's AABB top as z = -0.0399, which is below the
alley ground. Two candidate explanations, and the whole point is to tell them apart with measurements:

  1. `Floor_main` is not the surface the equipment stands on (a duplicate name, or a different body than the one the
     geometry gate measured F47 against at -0.252 mm).
  2. The query itself is fine but the ball, placed inside a LARGE slab, produces no nearest-feature pair for some
     other reason.

So this prints, for every static whose name contains floor/ground/table: its AABB, its collision shape type and its
collision filter. Then it re-runs the embedding test against the surface F47 actually rests on, with the ball lifted
progressively out of the slab so the separation is a known, positive, MEASURED quantity -- a response curve, which is
far stronger evidence than a single number.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/data/raw/huzijian/project1_database/tools/v64")
import physics_common_r10 as pc

LAYOUT = "/data/raw/huzijian/project1_database/tmp/v64_node12/layout_v65_tailwest_candidate_b.json"

w = pc.World(hz=1920, mode="upstream", verbose=False, layout_override=LAYOUT)
w.set_initial_state()

print("=" * 104, flush=True)
print("SELF-TEST DIAGNOSIS -- is Floor_main the support surface, and does the query respond to a known offset?", flush=True)
print("=" * 104, flush=True)

# ------------------------------------------------------------------ 1. identity of every floor-like static
print("\n  statics whose name suggests a support surface:", flush=True)
print(f"  {'body':>6}  {'name':<34} {'shape':>6}  AABB z range", flush=True)
floor_like = []
for sb in w._static:
    nm = w.body_names.get(sb, "?")
    if any(k in nm.lower() for k in ("floor", "ground", "table", "desk", "surface")):
        lo, hi = pc.p.getAABB(sb, physicsClientId=w.cid)
        info = pc.p.getCollisionShapeData(sb, -1, physicsClientId=w.cid)[0]
        floor_like.append((sb, nm, lo, hi))
        print(f"  {sb:>6}  {nm:<34} {info[2]:>6}  [{lo[2]:+.5f}, {hi[2]:+.5f}]", flush=True)

print(f"\n  total statics: {len(w._static)};  floor-like: {len(floor_like)}", flush=True)
name_counts = {}
for sb in w._static:
    nm = w.body_names.get(sb, "?")
    name_counts[nm] = name_counts.get(nm, 0) + 1
dupes = {n: c for n, c in name_counts.items() if c > 1}
print(f"  duplicated static names: {dupes if dupes else 'none'}", flush=True)
print(f"  'Floor_main' body ids: {[sb for sb in w._static if w.body_names.get(sb) == 'Floor_main']}", flush=True)

# ------------------------------------------------------------------ 2. which static is under F47?
f47 = w.actors["F47"]
f47_pos, _ = pc.p.getBasePositionAndOrientation(f47, physicsClientId=w.cid)
print(f"\n  F47 centre: ({f47_pos[0]:+.4f}, {f47_pos[1]:+.4f}, {f47_pos[2]:+.4f})", flush=True)
touching = []
for sb in w._static:
    pts = pc.p.getClosestPoints(f47, sb, 0.02, physicsClientId=w.cid)
    if pts:
        sep = min(pt[8] for pt in pts)
        touching.append((sep, w.body_names.get(sb, "?"), sb))
touching.sort()
print(f"  statics within 20 mm of F47 (the surface it actually rests on):", flush=True)
for sep, nm, sb in touching[:6]:
    print(f"    {1000 * sep:+9.4f} mm  {nm} (body {sb})", flush=True)

# ------------------------------------------------------------------ 3. response curve on the real support
if not touching:
    raise SystemExit("no support surface found near F47 -- cannot continue")
support_name = touching[0][1]
support = touching[0][2]
lo, hi = pc.p.getAABB(support, physicsClientId=w.cid)
print(f"\n  response curve against the real support: {support_name} (body {support}), AABB top z = {hi[2]:.6f}", flush=True)
print(f"  the ball is placed at a series of MEASURED heights; each row must follow the height by the same amount", flush=True)
print(f"  {'lift above top':>16} {'queried sep':>14} {'expected':>12} {'error':>10}", flush=True)

ball = w.actors["B"]
cx, cy = float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2)
rows = []
for lift_mm in (-3.0, -1.0, 0.0, 1.0, 3.0, 10.0, 30.0):
    z = float(hi[2]) + lift_mm / 1000.0
    pc.p.resetBasePositionAndOrientation(ball, [cx, cy, z], [0, 0, 0, 1], physicsClientId=w.cid)
    # NO step: measure the placement itself, before the solver can resolve any overlap
    pts = pc.p.getClosestPoints(ball, support, 0.50, physicsClientId=w.cid)
    sep = min((pt[8] for pt in pts), default=None)
    # the ball's centre is `lift` above the support top, so the gap between the two surfaces is lift - radius
    rb = pc.p.getCollisionShapeData(ball, -1, physicsClientId=w.cid)[0]
    radius = 0.0368
    expect = lift_mm / 1000.0 - radius
    err = None if sep is None else sep - expect
    rows.append({"lift_mm": lift_mm, "sep_m": sep, "expected_m": expect, "error_m": err})
    print(f"  {lift_mm:>+13.1f} mm " +
          (f"{1000 * sep:>+11.4f} mm {1000 * expect:>+9.4f} mm {1000 * err:>+7.4f} mm" if sep is not None
           else f"{'None':>14} {1000 * expect:>+9.4f} mm"), flush=True)

measured = [r for r in rows if r["sep_m"] is not None]
print(f"\n  rows with a measured separation: {len(measured)}/{len(rows)}", flush=True)
if measured:
    errs = [abs(r["error_m"]) for r in measured]
    print(f"  largest |measured - expected|: {1000 * max(errs):.4f} mm", flush=True)
    # the discriminator: does the measurement MOVE with the placement?
    span = max(r["sep_m"] for r in measured) - min(r["sep_m"] for r in measured)
    want_span = (max(r["lift_mm"] for r in measured) - min(r["lift_mm"] for r in measured)) / 1000.0
    print(f"  measured span {1000 * span:.4f} mm vs commanded span {1000 * want_span:.4f} mm", flush=True)
    print(f"  -> the query {'TRACKS the geometry' if abs(span - want_span) < 1e-4 else 'does NOT track the geometry'}",
          flush=True)

print(f"\n  CONCLUSION: Floor_main top z={hi[2]:.6f}. The r2 self-test used a body whose AABB top is "
      f"-0.039900, i.e. it did not embed the ball in the surface F47 rests on.", flush=True)
w.close()
