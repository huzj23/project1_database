"""V6.5 GATE 2 SELF-TEST (r4) -- can the detector fail? (discriminator corrected, and a real calibration found)

THE THREE DEFECTS IN MY OWN EARLIER SELF-TESTS
----------------------------------------------
  r1 placed the body, STEPPED, then queried. The solver de-penetrated the injected overlap before the query ran, so r1
     measured nothing and reported "detector MISSED the injection".
  r2 selected the support surface by the NAME `Floor_main`, which is shared by EIGHT distinct bodies (ids 22-29). It
     embedded the ball in body 22 while the chain rests on body 26, so `getClosestPoints` correctly returned no pair --
     and r2 drew a conclusion about the GATE from the answer to the wrong question.
  r3 discovered the support by query (body 26, correct) and got a clean response curve, but fitted its tracking slope
     over ALL eight placements, including the four that OVERLAP the surface. For an overlapping pair Bullet does not
     report a closest-feature distance, it reports penetration depth, which is a different quantity with a different
     response -- so the fit came out at 0.838 and r3 again declared the gate untrustworthy.

THE CORRECT DISCRIMINATOR
-------------------------
Split the curve by whether the placement actually overlaps:
  * NON-OVERLAPPING placements must track the commanded lift one-for-one. That is the real test of "does the query
    measure geometry", and on this range it is exact.
  * OVERLAPPING placements must report a negative separation, and are allowed to compress -- penetration depth is not
    a closest-distance and is not expected to be linear.
Conflating those two regimes is what produced r3's false alarm.

A REAL CALIBRATION FACT THIS UNCOVERED (reported, not hidden)
-------------------------------------------------------------
On the non-overlapping range the reading is offset from the ideal sphere-contact value by a CONSTANT ~1.0074 mm. The
ball's collision shape is a convex HULL (`baseball_common_hull.npz`), whose flat facets lie inside the sphere, so the
hull's surface sits ~1.0 mm closer to the centre than the circumscribed sphere. Consequences that must be stated:
  * `getClosestPoints` measures the hull, not an ideal sphere;
  * a reading of "0 mm" for the ball means its hull facet is touching, so the ball can be genuinely inside by up to
    about 1 mm before the query reports a negative number;
  * the small negative readings involving the ball (R vs A -0.67 mm, B vs table -0.26 mm) are therefore at or below
    this instrument's resolution for a hull-approximated sphere, and the box-vs-box readings (e.g. F47 vs floor) are
    not affected by it.
This makes the 1920 Hz acceptance verdict no weaker -- PERSISTENT was 0 and the worst value is sub-millimetre -- but it
does mean the ball's penetration numbers should be read with a ~1 mm instrument uncertainty, and that is now recorded.
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
HZ, EVERY, PERSIST_S, TOL = 1920, 24, 0.05, -0.001

print("=" * 104, flush=True)
print("V6.5 GATE 2 SELF-TEST (r4) -- can the detector fail?", flush=True)
print("  support discovered by query (the name 'Floor_main' covers 8 bodies); overlap and non-overlap regimes split",
      flush=True)
print("=" * 104, flush=True)

w = pc.World(hz=HZ, mode="upstream", verbose=False, layout_override=LAYOUT)
w.set_initial_state()

probe_actor = "F47"
cands = []
for sb in w._static:
    pts = pc.p.getClosestPoints(w.actors[probe_actor], sb, 0.02, physicsClientId=w.cid)
    if pts:
        cands.append((min(pt[8] for pt in pts), w.body_names.get(sb, "?"), sb))
cands.sort()
sep0, support_name, support = cands[0]
lo, hi = pc.p.getAABB(support, physicsClientId=w.cid)
dupes = [sb for sb in w._static if w.body_names.get(sb) == support_name]
print(f"\n  support under {probe_actor}: '{support_name}' body id {support} (resting {1000 * sep0:+.4f} mm)",
      flush=True)
print(f"  '{support_name}' also names {len(dupes) - 1} other bodies {dupes}; F47 rests on id {support}, "
      f"so selecting by name (id {dupes[0]}) would test the wrong slab", flush=True)

ball = w.actors["B"]
bpos, _ = pc.p.getBasePositionAndOrientation(ball, physicsClientId=w.cid)
blo, bhi = pc.p.getAABB(ball, physicsClientId=w.cid)
sphere_r = float(bhi[2] - bpos[2])
print(f"\n  ball collision radius from its own AABB: {1000 * sphere_r:.4f} mm "
      f"(the shape is a convex hull, not an ideal sphere -- see the calibration note)", flush=True)

cx, cy = float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2)
curve = []
print(f"\n  {'lift':>9} {'regime':>13} {'ideal gap':>12} {'queried':>12} {'offset':>11}", flush=True)
for lift_mm in (-5.0, -3.0, -1.0, -0.5, 0.0, 0.5, 1.0, 3.0, 10.0, 30.0, 60.0):
    z = float(hi[2]) + lift_mm / 1000.0
    pc.p.resetBasePositionAndOrientation(ball, [cx, cy, z], [0, 0, 0, 1], physicsClientId=w.cid)
    pts = pc.p.getClosestPoints(ball, support, 0.80, physicsClientId=w.cid)
    got = min((pt[8] for pt in pts), default=None)
    ideal = lift_mm / 1000.0 - sphere_r
    overlap = (got is not None and got < 0)
    curve.append({"lift_mm": lift_mm, "ideal_sphere_gap_m": ideal, "queried_m": got,
                  "overlapping": bool(overlap)})
    off = None if got is None else got - ideal
    print(f"  {lift_mm:>+6.1f} mm {'OVERLAP' if overlap else 'separate':>13} {1000 * ideal:>+9.4f} mm " +
          (f"{1000 * got:>+9.4f} mm {1000 * off:>+8.4f} mm" if got is not None else f"{'None':>12}"), flush=True)

# ---- discriminator 1: NON-OVERLAPPING placements must track the lift one-for-one
sep_pts = [(c["lift_mm"], c["queried_m"]) for c in curve if c["queried_m"] is not None and not c["overlapping"]]
lifts = np.array([p[0] for p in sep_pts]) / 1000.0
gots = np.array([p[1] for p in sep_pts])
slope = float(np.polyfit(lifts, gots, 1)[0])
resid = float(np.abs(gots - (slope * lifts + np.polyfit(lifts, gots, 1)[1])).max())
span_cmd = float(lifts.max() - lifts.min())
span_got = float(gots.max() - gots.min())
print(f"\n  NON-OVERLAPPING placements ({len(sep_pts)} of {len(curve)}):", flush=True)
print(f"    tracking slope      {slope:.9f}   (1.000000000 = the reading follows the geometry exactly)", flush=True)
print(f"    max residual        {1000 * resid:.6f} mm", flush=True)
print(f"    measured span {1000 * span_got:.4f} mm vs commanded span {1000 * span_cmd:.4f} mm", flush=True)
tracking_ok = abs(slope - 1.0) < 1e-6 and abs(span_got - span_cmd) < 1e-6

# ---- the constant hull offset, measured on the straight part of the curve
offsets = [c["queried_m"] - c["ideal_sphere_gap_m"] for c in curve
           if c["queried_m"] is not None and not c["overlapping"]]
hull_offset = float(np.mean(offsets)) if offsets else float("nan")
hull_spread = float(np.ptp(offsets)) if offsets else float("nan")
print(f"    constant offset from the ideal sphere: {1000 * hull_offset:+.4f} mm "
      f"(spread {1000 * hull_spread:.6f} mm) -> the query measures the HULL, not a sphere", flush=True)

# ---- discriminator 2: OVERLAPPING placements must report negative
ov = [c for c in curve if c["overlapping"]]
print(f"\n  OVERLAPPING placements ({len(ov)}):", flush=True)
for c in ov:
    print(f"    lift {c['lift_mm']:+.1f} mm -> {1000 * c['queried_m']:+.4f} mm", flush=True)
overlap_ok = len(ov) >= 3 and all(c["queried_m"] < TOL for c in ov)

# ---- negative control
far = next((sb for sb in w._static
            if np.hypot(pc.p.getAABB(sb, physicsClientId=w.cid)[0][0] - cx,
                        pc.p.getAABB(sb, physicsClientId=w.cid)[0][1] - cy) > 6.0), None)
pc.p.resetBasePositionAndOrientation(ball, [cx, cy, float(hi[2]) + 0.05], [0, 0, 0, 1], physicsClientId=w.cid)
far_sep = min((pt[8] for pt in pc.p.getClosestPoints(ball, far, 0.01, physicsClientId=w.cid)), default=None) \
    if far is not None else None
control_ok = far_sep is None
print(f"\n  negative control vs '{w.body_names.get(far, far)}' (>=6 m away): "
      f"{'no pair within 10 mm, correctly no contact' if control_ok else f'{1000 * far_sep:+.4f} mm'}", flush=True)

# ---- classifier
def classify(hist, persist_s=PERSIST_S, every=EVERY, hz=HZ, tol=TOL):
    if not hist:
        return []
    hist = sorted(hist)
    runs = []
    t0, dmin, prev = hist[0][0], hist[0][1], hist[0][0]
    for (t, d) in hist[1:]:
        if t - prev > 2.0 * every / hz:
            runs.append((t0, prev, dmin))
            t0, dmin = t, d
        dmin = min(dmin, d)
        prev = t
    runs.append((t0, prev, dmin))
    return ["PERSISTENT" if ((b - a) > persist_s and c < tol) else "transient" for (a, b, c) in runs if c < 0]


dt = EVERY / HZ
cases = [("sustained -3.000 mm for 0.50 s", [(i * dt, -0.003) for i in range(40)], "PERSISTENT"),
         ("single sample at -3.000 mm", [(0.5, -0.003)], "transient"),
         ("sustained -0.250 mm for 0.50 s (shallower than the 1 mm gate)", [(i * dt, -0.00025) for i in range(40)],
          "transient"),
         ("-4.000 mm for only 25 ms (deeper than the gate, shorter than the window)",
          [(i * dt, -0.004) for i in range(2)], "transient")]
print(f"\n  CLASSIFIER UNIT TEST", flush=True)
cls_ok = True
for label, hist, expect in cases:
    got = classify(hist)
    verdict = got[0] if got else "none"
    good = verdict == expect
    cls_ok &= good
    print(f"    {label:<64} -> {verdict:<11} expected {expect:<11} {'OK' if good else 'WRONG'}", flush=True)

able = bool(tracking_ok and overlap_ok and control_ok and cls_ok)
print(f"\n{'=' * 104}", flush=True)
print(f"  A. non-overlapping readings track the geometry exactly : {'YES' if tracking_ok else 'NO'} "
      f"(slope {slope:.9f}, residual {1000 * resid:.6f} mm)", flush=True)
print(f"  B. overlapping readings report negative                 : {'YES' if overlap_ok else 'NO'}", flush=True)
print(f"  C. negative control reports no false contact            : {'YES' if control_ok else 'NO'}", flush=True)
print(f"  D. classifier discriminates correctly                   : {'YES' if cls_ok else 'NO'}", flush=True)
print(f"  DETECTOR SELF-TEST: "
      f"{'PASS -- the gate is able to fail, so its PASS is meaningful' if able else 'FAIL'}", flush=True)

(OUT / "geometry_selftest.json").write_text(json.dumps({
    "self_test_pass": able,
    "support_discovery": {"probe_actor": probe_actor, "support_name": support_name,
                          "support_body_id": support, "resting_separation_m": sep0,
                          "bodies_sharing_that_name": dupes},
    "sphere_radius_from_aabb_m": sphere_r,
    "hull_calibration": {"constant_offset_m": hull_offset, "spread_m": hull_spread,
                         "interpretation": ("the ball's collision shape is a convex hull whose facets lie inside "
                                            "the circumscribed sphere, so its geometric readings carry a ~1 mm "
                                            "offset; this bounds the resolution of ball-involved penetration "
                                            "numbers, and does not affect box-vs-box readings")},
    "lift_response_curve": curve,
    "tracking_slope_non_overlapping": slope, "tracking_residual_m": resid,
    "measured_span_m": span_got, "commanded_span_m": span_cmd,
    "negative_control_no_pair": bool(control_ok),
    "classifier_cases": [{"label": l, "expected": e, "got": (classify(h)[0] if classify(h) else "none")}
                         for l, h, e in cases],
    "defects_in_my_own_tests": {
        "r1": "stepped before querying, so the solver de-penetrated the injected overlap first",
        "r2": "selected the support by the ambiguous name 'Floor_main' (8 bodies) and embedded the ball in the wrong slab",
        "r3": "fitted the tracking slope across overlapping and non-overlapping placements together, though Bullet reports penetration DEPTH for one and closest distance for the other",
    },
    "frequency_finding": {
        "hz1920": {"worst_sep_m": -0.0006697, "persistent": 0, "gate": "PASS"},
        "hz960": {"worst_sep_m": -0.0039775, "persistent": 2, "gate": "FAIL"},
        "interpretation": ("the R-vs-A desktop impact overlap scales with the timestep: -0.67 mm at the 1920 Hz "
                           "acceptance frequency, -3.98 mm at 960 Hz. Reported as a timestep-sensitivity boundary."),
    },
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {OUT / 'geometry_selftest.json'}", flush=True)
w.close()
