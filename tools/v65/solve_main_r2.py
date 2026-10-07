"""V6.5 -- ONE full world solve at 1920 Hz, exporting the high-frequency trajectory and the event table.

WHAT THIS IS
------------
V6.5 plan section 2 (20-75 min) requires a single complete world solved once at the acceptance frequency, from the
ball's entry to the last piece, exporting a 9 s high-frequency trajectory, an event table and the contact pairs. Every
later artifact -- the geometry gate, the camera design, the render -- must use THIS trajectory, so this script is the
critical path and it writes the file everything else reads.

WHY THE DETAILS BELOW ARE THE WAY THEY ARE
------------------------------------------
  * ONE world, ONE solve. The single most damaging bug in this project's history was pybullet's default client id 0:
    all `p.*` calls without `physicsClientId` silently drove the FIRST world, so a process that built a control and
    then a solve reported results from the wrong world -- with no error. `physics_common_r10.World` binds the client
    id on every call, and this script builds exactly one world.
  * 9.0 s, not 6.0 s. A shorter window truncated the cascade: the same layout gave legal-chain 23/48 at 3.5 s, 27/48
    at 4.0 s and 41/48 at 6.0 s, and 6.0 s itself had only 0.41 s of margin. The window is therefore 9 s, and the
    margin (last trigger time to end of sim) is recomputed and REPORTED here rather than assumed. If it falls below
    1 s the result is marked TRUNCATED and void.
  * Contacts are read from the post-step cache ONCE per substep and filtered in Python. Reading per-pair via
    `getContactPoints(a, b)` re-runs narrowphase for pairs the solver has already resolved and measured 45.8 ms per
    substep; the cache read measured 0.393 ms. The cache read is still not free -- an earlier claim that it was
    "240x cheaper" came from a profile that never iterated the returned list, and acting on it made a 5 s solve go
    from 296 s to 463 s.
  * Force is `c[9]` (normal force), positions are `c[5]`/`c[6]`, the normal on body B is `c[7]`, separation is `c[8]`
    (negative means penetrating) and `c[8]` is explicitly NOT the penetration conclusion -- V6.4 established that
    `cp[8]` is timestep-driven (the A-R impact reads -4.07 mm at 960 Hz and -0.79 mm at 1920 Hz). Penetration is
    gated separately by an independent geometric check.
  * The legal chain uses the ENTRY-R definition. F01 and F02 are both legitimately struck by R, so a "strict"
    definition that requires F02 to be struck by F01 yields 1/48 forever and would wrongly reject a valid entry.

OUTPUTS (into the run directory)
--------------------------------
  trajectory.npz   pos/quat/linvel/angvel for every actor at every substep, plus the substep times
  events.json      per-actor first contact (time, partner, force), peak tilt and its time, final tilt, displacement,
                   the per-partner peak force, the chain verdict, and the truncation margin
  contacts.json    the first-contact edges, i.e. the causal graph the camera must follow
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
ap.add_argument("--ext", type=float, default=0.0)
ap.add_argument("--tilt-threshold", type=float, default=60.0)
ap.add_argument("--no-ball", action="store_true", help="control: park the ball away and confirm nothing topples")
ap.add_argument("--label", default="v65_main")
args = ap.parse_args()

OUT = pc.ROOT / args.out_dir if not args.out_dir.startswith("/") else None
if args.out_dir.startswith("/"):
    from pathlib import Path
    OUT = Path(args.out_dir)
else:
    OUT = pc.ROOT / args.out_dir
OUT.mkdir(parents=True, exist_ok=True)

manifest = json.loads(pc.DEFAULT_MANIFEST.read_text())
layout = json.loads(open(args.layout, encoding="utf-8").read())
D = {r["id"]: np.array(manifest["objects"][r["id"]]["dims_m"], dtype=float) for r in layout["objects"]}

print("=" * 108, flush=True)
print(f"V6.5 SOLVE -- {args.label}   one world, {args.hz} Hz, {args.sim_s} s, layout {args.layout.split('/')[-1]}",
      flush=True)
if args.no_ball:
    print("  NO-BALL CONTROL: the ball will be parked away, so nothing should topple.", flush=True)
print("=" * 108, flush=True)

t_build = time.time()
w = pc.World(hz=args.hz, mode="upstream", verbose=True, layout_override=args.layout)
print(f"  world built in {time.time() - t_build:.1f} s", flush=True)

if args.no_ball:
    w.park_ball()
else:
    w.set_initial_state(extend_flight_s=(args.ext or None))

NAMES = list(w.actors)
bodies = {n: w.actors[n] for n in NAMES}
name_of = {b: n for n, b in w.actors.items()}
dyn_ids = set(w.actors.values())
ground = [r["id"] for r in w.layout["objects"]]
gi = {o: i for i, o in enumerate(ground)}

# ---------------------------------------------------------------------------------------------
# IDENTITY SELF-TEST. This project has confused the NAME space with the INTEGER body-id space
# three separate times, each time producing a confident wrong answer instead of an exception:
#   (1) `bodies = {i: w.actors[i]}` was name-keyed, so `other not in bodies` was always True and
#       every dynamic-dynamic contact was mislabelled "static";
#   (2) `dyn_ids = set(list(w.actors))` is a set of NAMES, so `b1 in dyn_ids` was always False and
#       a strike table came out silently empty;
#   (3) that same test in this script reported `legal 0/48` for a run in which all 48 pieces
#       toppled and the tail relayed perfectly.
# The assertions below make the two spaces fail LOUDLY at startup if they are ever conflated again.
# ---------------------------------------------------------------------------------------------
assert all(isinstance(x, int) for x in dyn_ids), "dyn_ids must hold integer body ids"
assert set(bodies.values()) == dyn_ids, "bodies (name->id) and dyn_ids must describe the same actors"
assert not (set(NAMES) & dyn_ids), "the name space and the body-id space must be disjoint"
assert name_of[bodies["R"]] == "R" and bodies["R"] in dyn_ids, "R must map name->id->name consistently"
print(f"  identity self-test PASSED: {len(NAMES)} names, {len(dyn_ids)} distinct integer body ids, "
      f"disjoint={not (set(NAMES) & dyn_ids)}", flush=True)
print(f"  actors: {len(NAMES)} ({len(ground)} ground pieces + B/A/R)   ground pieces: {len(ground)}", flush=True)

steps = int(round(args.sim_s * args.hz))
pos = {n: np.empty((steps + 1, 3), dtype=np.float32) for n in NAMES}
quat = {n: np.empty((steps + 1, 4), dtype=np.float32) for n in NAMES}
linvel = {n: np.empty((steps + 1, 3), dtype=np.float32) for n in NAMES}
angvel = {n: np.empty((steps + 1, 3), dtype=np.float32) for n in NAMES}
for n in NAMES:
    _p, _q = pc.p.getBasePositionAndOrientation(bodies[n], physicsClientId=w.cid)
    _lv, _av = pc.p.getBaseVelocity(bodies[n], physicsClientId=w.cid)
    pos[n][0], quat[n][0], linvel[n][0], angvel[n][0] = _p, _q, _lv, _av

# ---- event accumulation -------------------------------------------------------------
first_dyn = {}                      # actor -> {t, partner, force}  first DYNAMIC-dynamic contact
first_any = {}                      # actor -> {t, partner, force, is_dynamic}
peak_force = defaultdict(float)     # (actor, partner) -> max normal force
peak_force_dyn = defaultdict(float)
contact_pairs_at = defaultdict(list)  # partner -> times of first contact, per actor
peak_tilt_ever = {n: 0.0 for n in NAMES}
peak_tilt_t = {n: None for n in NAMES}
tilt_hist_sample = []               # (t, {actor: tilt}) on a coarse cadence for reporting

t_solve = time.time()
for s in range(steps):
    pc.p.stepSimulation(physicsClientId=w.cid)
    t = (s + 1) / args.hz
    for n in NAMES:
        _p, _q = pc.p.getBasePositionAndOrientation(bodies[n], physicsClientId=w.cid)
        _lv, _av = pc.p.getBaseVelocity(bodies[n], physicsClientId=w.cid)
        pos[n][s + 1], quat[n][s + 1] = _p, _q
        linvel[n][s + 1], angvel[n][s + 1] = _lv, _av
    # ONE cache read per substep, iterated in Python (see the module docstring)
    for c in pc.p.getContactPoints(physicsClientId=w.cid):
        b1, b2 = c[1], c[2]
        n1, n2 = name_of.get(b1), name_of.get(b2)
        if n1 is None or n2 is None:
            continue
        f = float(c[9])
        # `is_dyn` MUST be decided in the ID space, not the name space. An earlier version of this loop tested
        # `b in dyn_ids` where `b` was a NAME and `dyn_ids` was a set of INTEGER body ids, so the test was always
        # False, every dynamic-dynamic contact was discarded, and the run reported `legal 0/48` while all 48 pieces
        # had in fact toppled -- a complete, plausible, wrong result. This is the third time this project has mixed
        # the name and id spaces, so the mapping is asserted once here and `is_dyn` is computed from the ids.
        for a, b, b_id in ((n1, n2, b2), (n2, n1, b1)):
            is_dyn = b_id in dyn_ids
            first_any.setdefault(a, {"t": round(t, 6), "partner": b, "force_N": round(f, 4),
                                     "is_dynamic": bool(is_dyn)})
            if is_dyn:
                first_dyn.setdefault(a, {"t": round(t, 6), "partner": b, "force_N": round(f, 4)})
                if f > peak_force_dyn[(a, b)]:
                    peak_force_dyn[(a, b)] = f
            if f > peak_force[(a, b)]:
                peak_force[(a, b)] = f
    # tilt: track the peak for the pieces that matter without paying for all 51 every substep
    if s % 8 == 0:
        for n in ground:
            q = quat[n][s + 1]
            R22 = 1 - 2 * (q[0] * q[0] + q[1] * q[1])
            tilt = float(np.degrees(np.arccos(np.clip(R22, -1, 1))))
            if tilt > peak_tilt_ever[n]:
                peak_tilt_ever[n] = tilt
                peak_tilt_t[n] = round(t, 5)
    if s % 480 == 0:
        print(f"    t={t:5.2f}s  ({100.0 * s / steps:5.1f}%)  elapsed {time.time() - t_solve:6.1f}s", flush=True)
    if s % 480 == 0:
        tilt_hist_sample.append({"t": round(t, 4),
                                 "tilt": {n: round(float(np.degrees(np.arccos(np.clip(
                                     1 - 2 * (quat[n][s + 1][0] ** 2 + quat[n][s + 1][1] ** 2), -1, 1)))), 2)
                                     for n in ground if n >= "F40"}})
wall = time.time() - t_solve
print(f"  solve complete in {wall:.1f} s ({wall / args.sim_s:.1f} s per simulated second)", flush=True)

# ---- final tilts, displacement, chain verdict ---------------------------------------
final_tilt = {}
disp = {}
for n in ground:
    q = quat[n][-1]
    final_tilt[n] = float(np.degrees(np.arccos(np.clip(1 - 2 * (q[0] * q[0] + q[1] * q[1]), -1, 1))))
    disp[n] = float(np.linalg.norm(pos[n][-1] - pos[n][0]))

down = {o: peak_tilt_ever[o] >= args.tilt_threshold for o in ground}
legal, first_bad, bad_reason = 0, None, None
for k, o in enumerate(ground):
    trig = (first_dyn.get(o) or {}).get("partner")
    if not down[o]:
        first_bad, bad_reason = o, f"never reached {args.tilt_threshold} deg (peak {peak_tilt_ever[o]:.2f})"
        break
    if k == 0:
        if trig != "R":
            first_bad, bad_reason = o, f"first dynamic contact from {trig}, expected R"
            break
    elif k == 1:
        if trig not in ("R", ground[0]):
            first_bad, bad_reason = o, f"first dynamic contact from {trig}, expected R or {ground[0]}"
            break
    else:
        if trig != ground[k - 1]:
            first_bad, bad_reason = o, f"first dynamic contact from {trig}, expected {ground[k - 1]}"
            break
    legal = k + 1

# strict variant, reported but never used as the acceptance verdict (see the docstring)
strict = 0
for k, o in enumerate(ground):
    trig = (first_dyn.get(o) or {}).get("partner")
    if not down[o]:
        break
    if k == 0 and trig != "R":
        break
    if k >= 1 and trig != ground[k - 1]:
        break
    strict = k + 1

trigger_times = [(v["t"], n) for n, v in first_dyn.items() if n in gi]
last_trigger_t, last_trigger_n = max(trigger_times) if trigger_times else (None, None)
margin = None if last_trigger_t is None else round(args.sim_s - last_trigger_t, 5)
truncated = margin is not None and margin < 1.0

print(f"\n  B->A {first_dyn.get('A', {}).get('t')}   A->R {first_dyn.get('R', {}).get('t')}", flush=True)
print(f"  LEGAL CHAIN (entry-R) {legal}/{len(ground)}   STRICT {strict}/{len(ground)} (not the verdict)", flush=True)
if first_bad:
    print(f"  FIRST BREAK: {first_bad} -- {bad_reason}", flush=True)
print(f"  last trigger {last_trigger_n} at {last_trigger_t} s   margin {margin} s   "
      f"{'TRUNCATED -> VOID' if truncated else 'window OK'}", flush=True)

print(f"\n  {'piece':<6}{'first_dyn':>11}{'from':>7}{'F_N':>10}{'peak':>8}{'final':>8}{'disp_m':>9}", flush=True)
rows = []
for o in ground:
    fd = first_dyn.get(o) or {}
    rows.append({"piece": o, "first_dynamic": fd, "first_any": first_any.get(o),
                 "peak_tilt": round(peak_tilt_ever[o], 2), "peak_tilt_t": peak_tilt_t[o],
                 "final_tilt": round(final_tilt[o], 2), "displacement_m": round(disp[o], 5),
                 "down": bool(down[o]),
                 "peak_force_by_partner": {k[1]: round(v, 2) for k, v in peak_force_dyn.items() if k[0] == o}})
    print(f"  {o:<6}{str(fd.get('t', '-')):>11}{str(fd.get('partner', '-')):>7}"
          f"{fd.get('force_N', 0):>10.2f}{peak_tilt_ever[o]:>8.2f}{final_tilt[o]:>8.2f}{disp[o]:>9.5f}", flush=True)

n_down = sum(down.values())
print(f"\n  reached {args.tilt_threshold} deg: {n_down}/{len(ground)}", flush=True)
sub = [o for o in ground if not down[o]]
if sub:
    print(f"  BELOW the threshold: {sub}", flush=True)
boundary = [o for o in ground if down[o] and final_tilt[o] < args.tilt_threshold]
if boundary:
    print(f"  reached the threshold but settled below it (boundary cases to disclose): "
          f"{[(o, round(peak_tilt_ever[o], 2), round(final_tilt[o], 2)) for o in boundary]}", flush=True)

# ---- write outputs ------------------------------------------------------------------
np.savez_compressed(
    OUT / ("trajectory_noball.npz" if args.no_ball else "trajectory.npz"),
    t=np.arange(steps + 1, dtype=np.float64) / args.hz,
    **{f"pos_{n}": pos[n] for n in NAMES},
    **{f"quat_{n}": quat[n] for n in NAMES},
    **{f"linvel_{n}": linvel[n] for n in NAMES},
    **{f"angvel_{n}": angvel[n] for n in NAMES})

verdict = {
    "label": args.label, "layout": args.layout, "hz": args.hz, "sim_s": args.sim_s, "ext": args.ext,
    "no_ball": bool(args.no_ball), "steps": steps, "wall_s": round(wall, 1),
    "tilt_threshold": args.tilt_threshold,
    "legal_chain_entry_R": legal, "legal_chain_strict": strict, "ground_total": len(ground),
    "first_break": first_bad, "first_break_reason": bad_reason,
    "last_trigger": {"piece": last_trigger_n, "t": last_trigger_t}, "margin_s": margin,
    "truncated_void": bool(truncated),
    "n_reached_threshold": n_down,
    "below_threshold": sub,
    "boundary_settled_below": [[o, round(peak_tilt_ever[o], 2), round(final_tilt[o], 2)] for o in boundary],
    "t_B_A": (first_dyn.get("A") or {}).get("t"), "t_A_R": (first_dyn.get("R") or {}).get("t"),
    "A_touched_R": ("R" in [k[1] for k in peak_force_dyn if k[0] == "A"]),
    "B_touched_R": ("R" in [k[1] for k in peak_force_dyn if k[0] == "B"]),
    "rows": rows,
}
(OUT / ("events_noball.json" if args.no_ball else "events.json")).write_text(
    json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")

edges = [{"from": r["first_dynamic"]["partner"], "to": r["piece"], "t": r["first_dynamic"]["t"],
          "force_N": r["first_dynamic"]["force_N"]}
         for r in rows if r["first_dynamic"]]
(OUT / ("contacts_noball.json" if args.no_ball else "contacts.json")).write_text(
    json.dumps({"edges": edges, "peak_forces": {f"{k[0]}<-{k[1]}": round(v, 2)
                                                for k, v in sorted(peak_force_dyn.items())}},
               indent=2, ensure_ascii=False), encoding="utf-8")

print(f"\nwrote {OUT / 'trajectory.npz'}  events  contacts  (label {args.label})", flush=True)
print(f"VERDICT {args.label}: legal {legal}/{len(ground)}  reached {n_down}/{len(ground)}  "
      f"margin {margin} s  truncated={truncated}", flush=True)
w.close()
