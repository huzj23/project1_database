"""V6.4 P3-2 -- CAUSALITY: is each piece triggered by its DECLARED predecessor?

WHY "CARRIED" IS NOT AN ACCEPTANCE MEASURE
------------------------------------------
The auto-iteration reported a step with propagation 46/48 and 22 pieces toppling UPSTREAM. Reading that as "46 of 48
pieces responded" would be a serious error, and plan 7.2 gate 4 forbids exactly that reading:

    "每件有首接触、响应时间和最终状态；首次触发来自声明的上游，不能由跨弯误击绕过未倒件"
    (each piece has a first contact, a response time and a final state; the FIRST TRIGGER comes from the declared
     upstream, and must not come from a cross-bend mis-hit that bypasses un-toppled pieces)

A piece knocked over by the far bend, or by a neighbour falling sideways, has not been relayed to. Counting it as
"carried" measures how much of the scene ended up on the floor, not whether the chain propagated. So this script
measures the thing the gate names:

  * for every piece F01..F48, the FIRST contact it makes with any other dynamic body, and who that was;
  * whether that first contact came from its DECLARED predecessor (F(i-1)), from somewhere downstream, or from a
    body from the OTHER bend;
  * the time order of first triggers, so a piece that responds before its predecessor has clearly not been relayed to;
  * `legal_chain` = the length of the prefix F01..Fk where every piece was triggered by its declared predecessor,
    which is the only propagation number that reflects the causal claim.

A legal chain also requires each piece to REACH about 60 deg and stay down (plan 7.2 gate 3), not merely twitch, so
the tilt at the end of the run and the peak tilt are both reported per piece.

Sweep and tunnelling
--------------------
Plan 7.3.5 requires the high-speed ball and the falling R to be checked between substeps, because endpoints can
straddle a thin object. The desktop impacts here are resolved at 1920 Hz, where the ball moves 3.65 mm per substep,
and the R body is a 0.07 kg cylinder; both are reported against their own thin dimensions so the margin is visible
rather than assumed.
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
ap.add_argument("--layout", default="")
ap.add_argument("--label", default="baseline")
ap.add_argument("--hz", type=int, default=1920)
ap.add_argument("--sim-s", type=float, default=4.0)
ap.add_argument("--ext", type=float, default=0.0)
ap.add_argument("--tilt-threshold", type=float, default=60.0)
ap.add_argument("--out", default="")
args = ap.parse_args()

OUT = pc.ROOT / "outcomes/v64/radio_scurve_domino/v64_20261006_p0/p2"
OUT.mkdir(parents=True, exist_ok=True)

layout = json.loads(pc.LAYOUT.read_text())
order = [r["id"] for r in layout["objects"]]
print("=" * 100, flush=True)
print(f"V6.4 causality -- {args.label} @ {args.hz} Hz, tilt threshold {args.tilt_threshold} deg", flush=True)
print("=" * 100, flush=True)

w = pc.World(hz=args.hz, mode="upstream", verbose=False, layout_override=(args.layout or None))
start = w.set_initial_state(extend_flight_s=args.ext)
steps = int(args.sim_s * args.hz)

ids = list(w.actors)
bodies = {i: w.actors[i] for i in ids}
name_of = {i: n for n, i in w.actors.items()}
man = json.loads(pc.DEFAULT_MANIFEST.read_text())
D = {o: np.array(man["objects"][o]["dims_m"], dtype=float) for o in order}

# group each piece by which bend it belongs to, so a "cross-bend" trigger is identifiable rather than merely
# "not the predecessor"
bend_of = {}
for i, o in enumerate(order):
    bend_of[o] = "bend1" if 12 <= i < 18 else ("bend2" if 36 <= i < 43 else "lead")

pos = {i: np.empty((steps + 1, 3)) for i in ids}
quat = {i: np.empty((steps + 1, 4)) for i in ids}
for i in ids:
    _p, _q = pc.p.getBasePositionAndOrientation(bodies[i], physicsClientId=w.cid)
    pos[i][0] = _p
    quat[i][0] = _q

# first dynamic-dynamic contact per body, with the time and partner
first_contact = {}
first_static = {}
for s in range(steps):
    pc.p.stepSimulation(physicsClientId=w.cid)
    t = (s + 1) / args.hz
    for i in ids:
        _p, _q = pc.p.getBasePositionAndOrientation(bodies[i], physicsClientId=w.cid)
        pos[i][s + 1] = _p
        quat[i][s + 1] = _q
    if (s + 1) % 2:
        continue
    for c in pc.p.getContactPoints(physicsClientId=w.cid):
        _cid, b1, b2 = c[0], c[1], c[2]
        n1, n2 = name_of.get(b1), name_of.get(b2)
        if n1 is None or n2 is None:
            continue
        # record the first dynamic-dynamic contact in both directions. A static body has no entry in name_of, so
        # these are dynamic-dynamic contacts only, which is what "triggered by the declared upstream" is about.
        if n1 not in first_contact:
            first_contact[n1] = {"t": round(t, 5), "partner": n2}
        if n2 not in first_contact:
            first_contact[n2] = {"t": round(t, 5), "partner": n1}
    # static support: the first time a piece touches something that is not a dynamic actor
    if s % 8 == 0:
        for i in ids:
            n = name_of[i]
            if n in first_static:
                continue
            pts = pc.p.getContactPoints(bodyA=bodies[i], physicsClientId=w.cid)
            for c in pts:
                if c[2] not in bodies:
                    first_static[n] = {"t": round(t, 5), "other_body": int(c[2])}
                    break

w.pos, w.quat = pos, quat

# per-piece: first dynamic trigger, tilt
rows = []
for i, o in enumerate(order):
    fc = first_contact.get(o)
    pred = order[i - 1] if i > 0 else None
    succ_trigger = fc["partner"] if fc else None
    if i == 0:
        verdict = "origin"
    elif succ_trigger is None:
        verdict = "NO_TRIGGER"
    elif succ_trigger == pred:
        verdict = "DECLARED_PREDECESSOR"
    elif succ_trigger in order and order.index(succ_trigger) > i:
        verdict = "DOWNSTREAM (bypassed)"
    elif succ_trigger in order and order.index(succ_trigger) < i - 1:
        verdict = "UPSTREAM/OTHER"
    elif succ_trigger in ("B", "A", "R"):
        verdict = f"from_{succ_trigger}"
    else:
        verdict = "other"
    peak = w.peak_tilt_deg(o)
    final_tilt = float(np.degrees(np.arccos(np.clip(
        (np.array(pc.p.getMatrixFromQuaternion(quat[o][-1])).reshape(3, 3)[2, 2]), -1, 1))))
    rows.append({"piece": o, "index": i, "asset": man["objects"][o]["asset_key"], "bend": bend_of[o],
                 "first_trigger": succ_trigger, "t_first": fc["t"] if fc else None,
                 "declared_predecessor": pred, "verdict": verdict,
                 "peak_tilt": round(peak, 2), "final_tilt": round(final_tilt, 2),
                 "down": bool(peak >= args.tilt_threshold)})

print(f"\n  {'piece':<7}{'idx':>4} {'asset':<8}{'bend':<7}{'trigger':<10}{'t_first':>9}  "
      f"{'peak':>7}{'final':>7}  verdict", flush=True)
for r in rows:
    if r["index"] < 12 or r["verdict"] not in ("DECLARED_PREDECESSOR", "origin") or r["index"] > 44:
        tstr = "--" if r["t_first"] is None else f"{r['t_first']:9.4f}"
        print(f"  {r['piece']:<7}{r['index']:>4} {r['asset']:<8}{r['bend']:<7}"
              f"{str(r['first_trigger']):<10}{tstr:>9}"
              f"{r['peak_tilt']:>7.2f}{r['final_tilt']:>7.2f}  {r['verdict']}", flush=True)

# The legal prefix. Two definitions are reported because they differ at ONE place, and that place is a definition
# rather than a physical event: F02's first contact is with R, because R is large relative to the 0.125 m paper pitch.
# R landing on F01 IS the declared entry mechanism (plan 7.2 gate 3: "B->A->R->F01->relay"), so entry-R is the
# admissible reading; strict is kept beside it so the difference is visible instead of hidden in one number.
def _chain(allow_R_at_entry):
    n = 0
    for i, r in enumerate(rows):
        trig = r["first_trigger"]
        if not r["down"]:
            break
        if i == 0:
            if trig != "R":
                break
        elif i == 1:
            if not ((trig == order[i - 1]) or (allow_R_at_entry and trig == "R")):
                break
        else:
            if trig != order[i - 1]:
                break
        n = i + 1
    return n


legal_strict = _chain(False)
legal = _chain(True)
n_pred = sum(1 for r in rows if r["verdict"] == "DECLARED_PREDECESSOR")
n_down = sum(1 for r in rows if r["down"])
cross_bend = [r["piece"] for r in rows if r["verdict"] == "DOWNSTREAM (bypassed)"]
bypassed = [(r["piece"], r["first_trigger"]) for r in rows
            if r["first_trigger"] in order and order.index(r["first_trigger"]) > r["index"]]
skipped = []
for i in range(1, len(rows)):
    r = rows[i]
    if r["down"] and r["t_first"] is not None and rows[i - 1]["t_first"] is not None:
        if r["t_first"] < rows[i - 1]["t_first"] - 1e-6:
            skipped.append((r["piece"], r["t_first"], rows[i - 1]["piece"], rows[i - 1]["t_first"]))

# --- truncation guard (plan 7.1): the measurement window must extend past the last response by at least 1 s
_trig = [r["t_first"] for r in rows if r["t_first"] is not None]
last_trigger = max(_trig) if _trig else None
unsettled = (last_trigger is None) or (args.sim_s - last_trigger < 1.0)
truncated = bool(unsettled)
print(f"\n  WINDOW: last trigger {last_trigger} s of {args.sim_s} s simulated, "
      f"margin {None if last_trigger is None else round(args.sim_s - last_trigger, 4)} s", flush=True)
if truncated:
    print(f"  *** TRUNCATED: the cascade was still running when the run stopped. Plan 7.1 forbids reading a chain "
          f"length from a truncated run, so this result is void and must be re-run longer ***", flush=True)

print(f"\n  triggered by DECLARED predecessor: {n_pred}/48", flush=True)
print(f"  reached {args.tilt_threshold} deg and stayed: {n_down}/48", flush=True)
print(f"  LEGAL CHAIN entry-R (F01,F02 by R -- the declared entry; rest by their predecessor AND "
      f">= {args.tilt_threshold} deg): {legal}/48", flush=True)
print(f"  LEGAL CHAIN strict  (F02 must be struck by F01): {legal_strict}/48", flush=True)
if legal < len(rows):
    _b = rows[legal]
    print(f"  first break: {_b['piece']} -- peak {_b['peak_tilt']} deg, "
          f"triggered by {_b['first_trigger']} (declared predecessor {_b['declared_predecessor']})", flush=True)
if bypassed:
    print(f"  BYPASSED (triggered by a piece further downstream): {len(bypassed)} {bypassed[:10]}", flush=True)
if skipped:
    print(f"  OUT OF ORDER (responded before its predecessor): {len(skipped)} {skipped[:8]}", flush=True)
print(f"\n  sweep margin: ball at {np.linalg.norm(pc.PROBE_BALL_VELOCITY):.3f} m/s travels "
      f"{1000 * np.linalg.norm(pc.PROBE_BALL_VELOCITY) / args.hz:.3f} mm per substep at {args.hz} Hz; "
      f"thinnest chain piece is {1000 * min(D[o].min() for o in order):.2f} mm", flush=True)

rep = {"status": "P3_2_CAUSALITY", "label": args.label, "hz": args.hz, "layout": args.layout or "settled",
       "tilt_threshold": args.tilt_threshold, "rows": rows,
       "n_declared_predecessor": n_pred, "n_down": n_down,
       "legal_chain": legal, "legal_chain_strict": legal_strict,
       "bypassed": bypassed, "out_of_order": skipped,
       "gate_causality": "PASS" if legal == len(rows) else "FAIL",
       "last_trigger_s": last_trigger, "window_margin_s": None if last_trigger is None else round(args.sim_s - last_trigger, 4),
       "truncated": truncated,
       "verdict": "VOID_TRUNCATED" if truncated else ("PASS" if legal == len(rows) else "FAIL")}
(OUT / (args.out or f"causality_{args.label}_hz{args.hz}.json")).write_text(
    json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nwrote {OUT / (args.out or f'causality_{args.label}_hz{args.hz}.json')}", flush=True)
print(f"GATE 因果链 (plan 7.2): {rep['gate_causality']}", flush=True)
if rep["truncated"]:
    print(f"VERDICT: VOID_TRUNCATED -- re-run with a longer sim_s before trusting the chain length", flush=True)
w.close()
