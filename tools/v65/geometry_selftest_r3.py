"""V6.5 GATE 2 SELF-TEST (r3) -- prove the penetration detector CAN fail, using the surface it actually measures.

WHAT r2 GOT WRONG, AND WHY IT MATTERS
-------------------------------------
r2 placed the ball inside the body it found by the NAME `Floor_main`, and `getClosestPoints` returned no pair at all,
so r2 printed "query CANNOT see a deliberate embedding" and declared the gate untrustworthy.

The diagnostic (`gselftest_diagnose.py`) found the real reason, and it is not a defect in the query:

  * `Floor_main` is EIGHT separate bodies (ids 22-29), all sharing that name. Picking "the one called Floor_main"
    returns body 22, which is a different slab from the one the chain stands on.
  * F47 -- which the geometry gate itself measured at -0.252 mm against its support -- rests on `Floor_main`
    **body 26**, not body 22.
  * The ball was placed at body 22's AABB centre in x and y. That point is not near body 26, so there was genuinely
    no nearby pair to report, and `None` was the CORRECT answer to the question r2 asked. r2 then drew a conclusion
    about the gate from it.

So r2's failure was in choosing the subject, not in the measurement. This is the same family as every other error in
this project: a confident, plausible, wrong conclusion produced by asking a subtly wrong question.

WHAT r3 DOES INSTEAD
--------------------
The support surface is DISCOVERED by querying which static is closest to a chain actor, rather than selected by name,
because a duplicated name identified the wrong body. The test then:

  A. EMBEDDING SENSITIVITY, as a response curve. The ball is placed at a series of known heights relative to the
     measured AABB top and queried WITHOUT stepping (so the solver cannot de-penetrate it first -- r1's mistake).
     The discriminator is not a single number but whether the reported separation TRACKS the commanded lift.
  B. NEGATIVE CONTROL. The same placement against a body it is NOT touching must report no penetration, so the query
     is not simply returning "negative" for everything.
  C. CLASSIFIER UNIT TEST, unchanged from r2 and already passing: a sustained deep overlap must be PERSISTENT, and a
     single-sample blip, a shallow overlap and a short deep overlap must all be transient.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/data/raw/huzijian/project1_database/tools/v64")
import physics_common_r10 as pc

LAYOUT = "/data/raw/huzijian/project1_database/tmp/v64_node12/layout_v65_tailwest_candidate_b.json"
OUT = Path("/data/raw/huzijian/project1_database/outcomes/v65/radio_scurve_domino/v65_20261007_final")
HZ = 1920
EVERY = 24
PERSIST_S = 0.05
TOL = -0.001

print("=" * 104, flush=True)
print("V6.5 GATE 2 SELF-TEST (r3) -- can the detector fail?", flush=True)
print("  The support surface is DISCOVERED by query, not chosen by name: `Floor_main` names EIGHT different bodies.",
      flush=True)
print("=" * 104, flush=True)

w = pc.World(hz=HZ, mode="upstream", verbose=False, layout_override=LAYOUT)
w.set_initial_state()

# ---------------------------------------------------------------- A. find the real support under a chain actor
probe_actor = "F47"
f47 = w.actors[probe_actor]
cands = []
for sb in w._static:
    pts = pc.p.getClosestPoints(f47, sb, 0.02, physicsClientId=w.cid)
    if pts:
        cands.append((min(pt[8] for pt in pts), w.body_names.get(sb, "?"), sb))
cands.sort()
sep0, support_name, support = cands[0]
lo, hi = pc.p.getAABB(support, physicsClientId=w.cid)
print(f"\n  support under {probe_actor}: '{support_name}' body id {support}, "
      f"resting separation {1000 * sep0:+.4f} mm", flush=True)
print(f"  its AABB: x[{lo[0]:+.4f},{hi[0]:+.4f}] y[{lo[1]:+.4f},{hi[1]:+.4f}] z[{lo[2]:+.4f},{hi[2]:+.4f}]",
      flush=True)
dupes = [sb for sb in w._static if w.body_names.get(sb) == support_name]
print(f"  WARNING -- '{support_name}' is the name of {len(dupes)} distinct bodies: {dupes}", flush=True)
print(f"  -> choosing a body by that name would have picked id {dupes[0]}, "
      f"which is {'the right one' if dupes[0] == support else 'A DIFFERENT SLAB'}", flush=True)

# the ball's real collision radius, taken from its own shape rather than assumed
ball = w.actors["B"]
bpos, _ = pc.p.getBasePositionAndOrientation(ball, physicsClientId=w.cid)
blo, bhi = pc.p.getAABB(ball, physicsClientId=w.cid)
radius = float(bhi[2] - bpos[2])
print(f"\n  ball B centre z {bpos[2]:+.5f}, AABB z [{blo[2]:+.5f},{bhi[2]:+.5f}] -> collision radius "
      f"{1000 * radius:.4f} mm (measured, not assumed)", flush=True)

# ---------------------------------------------------------------- B. response curve, queried WITHOUT stepping
print(f"\n  {'lift above top':>15} {'expected gap':>14} {'queried gap':>14} {'error':>11}", flush=True)
cx, cy = float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2)
curve = []
for lift_mm in (-5.0, -3.0, -1.0, 0.0, 1.0, 3.0, 10.0, 30.0):
    z = float(hi[2]) + lift_mm / 1000.0
    pc.p.resetBasePositionAndOrientation(ball, [cx, cy, z], [0, 0, 0, 1], physicsClientId=w.cid)
    pts = pc.p.getClosestPoints(ball, support, 0.60, physicsClientId=w.cid)
    got = min((pt[8] for pt in pts), default=None)
    expect = lift_mm / 1000.0 - radius
    err = None if got is None else got - expect
    curve.append({"lift_mm": lift_mm, "expected_m": expect, "got_m": got, "error_m": err})
    print(f"  {lift_mm:>+12.1f} mm {1000 * expect:>+11.4f} mm " +
          (f"{1000 * got:>+11.4f} mm {1000 * err:>+8.4f} mm" if got is not None else f"{'None':>14}"),
          flush=True)

measured = [(c["lift_mm"], c["got_m"], c["expected_m"]) for c in curve if c["got_m"] is not None]
seen_negative = any(g < TOL for _, g, _ in measured)
# the discriminator: does the reported gap follow the commanded lift, one-for-one?
if len(measured) >= 3:
    lifts = np.array([m[0] for m in measured]) / 1000.0
    gots = np.array([m[1] for m in measured])
    slope = float(np.polyfit(lifts, gots, 1)[0])
    span_cmd = float(lifts.max() - lifts.min())
    span_got = float(gots.max() - gots.min())
else:
    slope, span_cmd, span_got = float("nan"), 0.0, 0.0
print(f"\n  rows measured: {len(measured)}/{len(curve)}", flush=True)
print(f"  a deliberate 5 mm embedding reported a NEGATIVE separation: {'YES' if seen_negative else 'NO'}", flush=True)
print(f"  the reported gap tracks the commanded lift with slope {slope:.6f} (1.000000 = exact)", flush=True)
print(f"  measured span {1000 * span_got:.3f} mm vs commanded span {1000 * span_cmd:.3f} mm", flush=True)
query_sees = seen_negative and abs(slope - 1.0) < 0.02

# ---------------------------------------------------------------- C. negative control: a body it does NOT touch
far = None
for sb in w._static:
    slo, shi = pc.p.getAABB(sb, physicsClientId=w.cid)
    if np.hypot(slo[0] - cx, slo[1] - cy) > 6.0:
        far = sb
        break
pc.p.resetBasePositionAndOrientation(ball, [cx, cy, float(hi[2]) + 0.05], [0, 0, 0, 1], physicsClientId=w.cid)
far_pts = pc.p.getClosestPoints(ball, far, 0.01, physicsClientId=w.cid) if far is not None else []
far_sep = min((pt[8] for pt in far_pts), default=None)
print(f"\n  negative control vs '{w.body_names.get(far, far)}' (>=6 m away): "
      f"{'no pair within 10 mm -- correctly reports no contact' if far_sep is None else f'{1000 * far_sep:+.4f} mm'}",
      flush=True)
control_ok = far_sep is None

# ---------------------------------------------------------------- D. classifier
print(f"\n  CLASSIFIER UNIT TEST (the classifier, not the query, decides PASS/FAIL)", flush=True)


def classify(hist, persist_s=PERSIST_S, every=EVERY, hz=HZ, tol=TOL):
    if not hist:
        return []
    hist = sorted(hist)
    runs = []
    run_t0, run_min, prev = hist[0][0], hist[0][1], hist[0][0]
    for (t, d) in hist[1:]:
        if t - prev > 2.0 * every / hz:
            runs.append((run_t0, prev, run_min))
            run_t0, run_min = t, d
        run_min = min(run_min, d)
        prev = t
    runs.append((run_t0, prev, run_min))
    out = []
    for (t0, t1, dmin) in runs:
        if (t1 - t0) > persist_s and dmin < tol:
            out.append("PERSISTENT")
        elif dmin < 0:
            out.append("transient")
    return out


dt = EVERY / HZ
cases = [("sustained -3.000 mm for 0.50 s", [(i * dt, -0.003) for i in range(40)], "PERSISTENT"),
         ("single sample at -3.000 mm", [(0.5, -0.003)], "transient"),
         ("sustained -0.250 mm for 0.50 s (shallower than the 1 mm gate)", [(i * dt, -0.00025) for i in range(40)],
          "transient"),
         ("-4.000 mm for only 25 ms (deeper than the gate, shorter than the window)",
          [(i * dt, -0.004) for i in range(2)], "transient")]
cls_ok = True
for label, hist, expect in cases:
    got = classify(hist)
    verdict = got[0] if got else "none"
    good = (verdict == expect)
    cls_ok &= good
    print(f"    {label:<64} -> {verdict:<11} expected {expect:<11} {'OK' if good else 'WRONG'}", flush=True)

print(f"\n{'=' * 104}", flush=True)
able = bool(query_sees and control_ok and cls_ok)
print(f"  A. query tracks geometry and sees an embedding  : {'YES' if query_sees else 'NO'} "
      f"(slope {slope:.6f}, negative seen {seen_negative})", flush=True)
print(f"  B. negative control reports no false contact    : {'YES' if control_ok else 'NO'}", flush=True)
print(f"  C. classifier discriminates correctly           : {'YES' if cls_ok else 'NO'}", flush=True)
print(f"  DETECTOR SELF-TEST: "
      f"{'PASS -- the gate is able to fail, so its PASS is meaningful' if able else 'FAIL -- the gate cannot be trusted'}",
      flush=True)

(OUT / "geometry_selftest.json").write_text(json.dumps({
    "self_test_pass": able,
    "support_discovery": {"probe_actor": probe_actor, "support_name": support_name, "support_body_id": support,
                          "resting_separation_m": sep0,
                          "bodies_sharing_that_name": dupes,
                          "note": "the support is found by QUERY; the name is ambiguous across 8 bodies"},
    "ball_radius_m": radius,
    "lift_response_curve": curve,
    "tracking_slope": slope, "measured_span_m": span_got, "commanded_span_m": span_cmd,
    "embedding_reported_negative": bool(seen_negative),
    "negative_control_no_pair": bool(control_ok),
    "classifier_cases": [{"label": l, "expected": e, "got": (classify(h)[0] if classify(h) else "none")}
                         for l, h, e in cases],
    "parameters": {"hz": HZ, "every": EVERY, "persist_s": PERSIST_S, "tol_m": TOL},
    "r1_defect": "stepped before querying, so the solver de-penetrated the injected overlap first",
    "r2_defect": ("selected the support by the name 'Floor_main', which is shared by 8 bodies; it embedded the ball "
                  "in body 22 while the chain rests on body 26, so 'None' was the correct answer to the wrong "
                  "question and r2 wrongly blamed the gate"),
    "frequency_finding": {
        "hz1920": {"worst_sep_m": -0.0006697, "persistent": 0, "gate": "PASS"},
        "hz960": {"worst_sep_m": -0.0039775, "persistent": 2, "gate": "FAIL"},
        "interpretation": ("the R-vs-A desktop impact overlap scales with the timestep: -0.67 mm at the 1920 Hz "
                           "acceptance frequency, -3.98 mm at 960 Hz. Reported as a timestep-sensitivity boundary, "
                           "not hidden."),
    },
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {OUT / 'geometry_selftest.json'}", flush=True)
w.close()
