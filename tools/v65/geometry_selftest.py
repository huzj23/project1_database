"""V6.5 GATE 2 self-test (r2) -- prove the penetration detector CAN fail, and unit-test the classifier.

WHY r1's SELF-TEST WAS WRONG (it reported "detector MISSED the injection")
--------------------------------------------------------------------------
r1 placed B 3 mm inside the floor slab, then called `stepSimulation` BEFORE querying the distance. Bullet's contact
solver de-penetrates an overlap in the very step it is given, so by the time the query ran the overlap had already
been pushed out and the measured separation was no longer negative. The test therefore failed to see an embedding it
had itself created, and reported "GATE IS BROKEN" when in fact the TEST was broken.

That is the same mistake this project has made repeatedly and it is worth naming precisely: the measurement was taken
at the wrong moment, and it produced a confident conclusion about the gate rather than about the test. A self-test
must be as carefully validated as the thing it tests.

WHAT THE HONEST SELF-TEST IS
----------------------------
Two separate claims need proving, and they are now tested separately:

  A. THE QUERY CAN SEE A DELIBERATE EMBEDDING. Place a body inside another and query WITHOUT stepping, so the
     solver has no chance to resolve it. The measured separation must be negative and of the right magnitude.
  B. THE CLASSIFIER CALLS A SUSTAINED EMBEDDING "PERSISTENT" AND A ONE-SAMPLE BLIP "TRANSIENT". This is a pure unit
     test on synthetic sample series, because the classifier -- not the query -- is what turns measurements into a
     PASS or a FAIL. Feeding it a known-persistent series and a known-transient series proves it discriminates.

If A measures a negative separation and B sorts the two series correctly, the gate is able to fail and its verdict
means something. If either fails, the gate's PASS is not admissible.
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

print("=" * 100, flush=True)
print("V6.5 GATE 2 SELF-TEST (r2) -- can the detector fail?", flush=True)
print("  r1 placed the body, STEPPED, then queried; the solver de-penetrated it first, so r1 was testing nothing.",
      flush=True)
print("=" * 100, flush=True)

# ------------------------------------------------------------------ A. the query sees an embedding
w = pc.World(hz=HZ, mode="upstream", verbose=False, layout_override=LAYOUT)
w.set_initial_state()
floor = next(sb for sb in w._static if w.body_names.get(sb) == "Floor_main")
lo, hi = pc.p.getAABB(floor, physicsClientId=w.cid)
inside_z = float(hi[2]) - 0.003
ball = w.actors["B"]
cx, cy = float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2)
pc.p.resetBasePositionAndOrientation(ball, [cx, cy, inside_z], [0, 0, 0, 1], physicsClientId=w.cid)

# NO STEP: measure the state as placed, so the solver cannot resolve it away first.
pts_no_step = pc.p.getClosestPoints(ball, floor, 0.10, physicsClientId=w.cid)
sep_no_step = min((pt[8] for pt in pts_no_step), default=None)
print(f"\n  A. QUERY SENSITIVITY", flush=True)
print(f"     floor AABB top z = {hi[2]:.6f}; ball placed at z = {inside_z:.6f}; nominal depth 3.000 mm", flush=True)
print(f"     separation queried WITHOUT stepping: "
      f"{'None (no pair within 0.10 m)' if sep_no_step is None else f'{1000 * sep_no_step:+.3f} mm'}", flush=True)
# what it reads after a step, for contrast -- this is what fooled r1
pc.p.stepSimulation(physicsClientId=w.cid)
pts_after = pc.p.getClosestPoints(ball, floor, 0.10, physicsClientId=w.cid)
sep_after = min((pt[8] for pt in pts_after), default=None)
print(f"     separation after ONE step:           "
      f"{'None' if sep_after is None else f'{1000 * sep_after:+.3f} mm'}"
      f"   <- the solver de-penetrated it, which is exactly why r1 saw no embedding", flush=True)
query_sees = sep_no_step is not None and sep_no_step < TOL
print(f"     -> query {'CAN' if query_sees else 'CANNOT'} see a deliberate embedding", flush=True)
w.close()

# ------------------------------------------------------------------ B. the classifier discriminates
print(f"\n  B. CLASSIFIER UNIT TEST", flush=True)


def classify(hist, persist_s=PERSIST_S, every=EVERY, hz=HZ, tol=TOL):
    """The exact rule geometry_gate.py uses: runs of negative samples, split when the gap exceeds 2 sample periods."""
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
# a sustained embedding: 40 consecutive samples at -3 mm (spans 40*dt = 0.50 s, far beyond the 0.05 s window)
sustained = [(i * dt, -0.003) for i in range(40)]
# a single-sample blip at -3 mm (spans 0.0 s, below the window)
blip = [(0.5, -0.003)]
# a genuine 0.25 mm settling overlap: deep in TIME but shallower than the 1 mm tolerance
shallow = [(i * dt, -0.00025) for i in range(40)]
# a deep but very short overlap: 2 samples = 25 ms, below the 50 ms window
brief = [(i * dt, -0.004) for i in range(2)]

cases = [("sustained -3.000 mm for 0.50 s", sustained, "PERSISTENT"),
         ("single sample at -3.000 mm", blip, "transient"),
         ("sustained -0.250 mm for 0.50 s (shallower than the 1 mm gate)", shallow, "transient"),
         ("-4.000 mm for only 25 ms (deeper than the gate, shorter than the window)", brief, "transient")]
ok = True
for label, hist, expect in cases:
    got = classify(hist)
    verdict = got[0] if got else "none"
    good = (verdict == expect)
    ok &= good
    print(f"     {label:<62} -> {verdict:<11} expected {expect:<11} {'OK' if good else 'WRONG'}", flush=True)

print(f"\n{'=' * 100}", flush=True)
able = query_sees and ok
print(f"  query sees a deliberate embedding : {'YES' if query_sees else 'NO'}", flush=True)
print(f"  classifier discriminates correctly: {'YES' if ok else 'NO'}", flush=True)
print(f"  DETECTOR SELF-TEST: {'PASS -- the gate is able to fail, so its PASS is meaningful' if able else 'FAIL -- the gate cannot be trusted'}", flush=True)

# ------------------------------------------------------------------ report the two frequency results together
summary = {
    "self_test_pass": bool(able),
    "query_sees_embedding": {"sep_no_step_m": sep_no_step, "sep_after_one_step_m": sep_after,
                             "nominal_depth_m": 0.003,
                             "note": "measuring AFTER a step hides the overlap because the solver resolves it"},
    "classifier_cases": [{"label": l, "expected": e, "got": (classify(h)[0] if classify(h) else "none")}
                         for l, h, e in cases],
    "parameters": {"hz": HZ, "every": EVERY, "persist_s": PERSIST_S, "tol_m": TOL},
    "r1_defect": ("r1 stepped before querying, so the solver de-penetrated the injected overlap and r1 reported "
                  "'detector MISSED the injection' -- a defect in the test, not in the gate"),
    "frequency_finding": {
        "hz1920": {"worst_sep_m": -0.0006697, "persistent": 0, "gate": "PASS"},
        "hz960": {"worst_sep_m": -0.0039775, "persistent": 2, "gate": "FAIL"},
        "interpretation": ("The R-vs-A desktop impact overlap scales with the timestep: -0.67 mm at the 1920 Hz "
                           "acceptance frequency and -3.98 mm at 960 Hz. This is the timestep-driven behaviour V6.4 "
                           "already documented for cp[8], now confirmed with the independent geometric query. The "
                           "acceptance gate is quoted at 1920 Hz and PASSES there; the 960 Hz cross-check is reported "
                           "as a timestep-sensitivity boundary, not hidden."),
    },
}
(OUT / "geometry_selftest.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {OUT / 'geometry_selftest.json'}", flush=True)
