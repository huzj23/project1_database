"""Verify the stage-05 physics claims against the recorded evidence.

Every number this prints comes from a file in the run directory. The point is to check the claims
the acceptance record makes rather than to re-assert them: the pre-contact descent, that the trigger
genuinely contacts the target before it moves, that nothing penetrates, and that the response is
attributable to the strike.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")
RUN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle" / (
    sys.argv[1] if len(sys.argv) > 1 else "20260929T110000")

cfg = json.loads((RUN / "resolved_config.json").read_text(encoding="utf-8"))
tr = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))
traj = tr["bodies"]
cause = json.loads((RUN / "causality.json").read_text(encoding="utf-8"))["bodies"]
events = json.loads((RUN / "events.json").read_text(encoding="utf-8"))
val = json.loads((RUN / "validation.json").read_text(encoding="utf-8"))
target = cfg["target_instance_id"]
trigger = cfg["trigger_instance_id"]
PF = cfg["physics_fps"]
VF = cfg["video_fps"]

print("=" * 100)
print(f"=== run {RUN.name}: target {target}, trigger {trigger} ===")
print(f"  {cfg['frame_count']} video frames at {VF} fps = "
      f"{cfg['frame_count']/VF:.4f} s; physics {PF} Hz, "
      f"{cfg['substeps_per_video_frame']} substeps/frame")

print("\n=== 1. contract checks (validation.json) ===")
for k, v in val["checks"].items():
    print(f"  [{'x' if v else ' '}] {k}")
print(f"  overall pass={val['pass']}  messages={val['messages']}")

print("\n=== 2. the trigger-to-target contact episode ===")
eps = [e for e in events
       if {e["instance_a"], e["instance_b"]} == {trigger, target}
       or trigger in e["pair"] and target in e["pair"]]
if eps:
    for e in eps:
        print(f"  {e['instance_a']} <-> {e['instance_b']}")
        print(f"    steps {e['step_start']}..{e['step_end']}  "
              f"t {e['time_start_s']:.4f}..{e['time_end_s']:.4f} s  "
              f"duration {e['duration_s']:.4f} s  substeps {e['substeps']}")
else:
    print("  NO trigger-to-target episode found")
print(f"  all episodes: {len(events)}")
for e in events:
    print(f"    {e['instance_a']:16s} <-> {e['instance_b']:16s} "
          f"t {e['time_start_s']:.4f}..{e['time_end_s']:.4f}  substeps {e['substeps']}")

print("\n=== 3. causality: did the target move only AFTER contact? ===")
for name, c in cause.items():
    if not c.get("moved"):
        print(f"  {name:18s} moved=False  ({c.get('note')})")
        continue
    print(f"  {name:18s} first moved at frame {c['first_moving_frame']} "
          f"(t={c['first_moving_time_s']:.4f} s)")
    print(f"      moved_without_preceding_contact = {c['moved_without_preceding_contact']}")
    for p in c["contacts_immediately_before"]:
        print(f"      preceding contact step {p['step']} {p['pair']} "
              f"F_n={p['normal_force_n']:.5f} N d={p['signed_distance_m']:.6f} m")

first_contact = min((e["step_start"] for e in eps), default=None)
tt = cause.get(target, {})
if first_contact and tt.get("moved"):
    t_contact = first_contact / PF
    t_move = tt["first_moving_time_s"]
    print(f"\n  contact first at step {first_contact} (t={t_contact:.4f} s)")
    print(f"  target first moves at t={t_move:.4f} s")
    print(f"  -> target moves {t_move - t_contact:+.4f} s relative to first contact  "
          f"{'ORDERED CORRECTLY' if t_contact <= t_move + 1e-9 else '!! BEFORE CONTACT'}")

print("\n=== 4. pre-contact descent: is the target still until the strike? ===")
rows = traj[target]
pc = [r for r in rows if r["time_s"] < (first_contact / PF if first_contact else 1e9)]
if pc:
    p0 = np.array(pc[0]["position_m"])
    dmax = max(float(np.linalg.norm(np.array(r["position_m"]) - p0)) for r in pc)
    vmax = max(float(np.linalg.norm(r["linear_velocity_m_s"])) for r in pc)
    q0 = np.array(pc[0]["quaternion_xyzw"])
    tmax = max(math.degrees(2 * math.acos(min(1.0, abs(float(np.dot(q0, r["quaternion_xyzw"]))))))
               for r in pc)
    print(f"  {len(pc)} frames before contact")
    print(f"  max target displacement {dmax*1000:.4f} mm, max tilt {tmax:.4f} deg, "
          f"max speed {vmax:.6f} m/s")
print("\n  trigger descent:")
tr_rows = traj[trigger]
fc = first_contact or 0
dr = [r for r in tr_rows if r["frame"] < fc / (PF / VF)]
if dr:
    z0, z1 = dr[0]["position_m"][2], dr[-1]["position_m"][2]
    print(f"    released at frame {dr[0]['frame']} z={z0:.6f}, contact frame "
          f"{dr[-1]['frame']} z={z1:.6f}, fell {z0-z1:.6f} m")
    print(f"    free-fall time for that distance: {math.sqrt(2*(z0-z1)/9.81):.4f} s")
    print(f"    measured pre-contact time: {dr[-1]['time_s']:.4f} s")
print("\n  response (target, whole run):")
if rows:
    p0, p1 = np.array(rows[0]["position_m"]), np.array(rows[-1]["position_m"])
    q0, q1 = np.array(rows[0]["quaternion_xyzw"]), np.array(rows[-1]["quaternion_xyzw"])
    print(f"    net translation {np.linalg.norm(p1-p0)*1000:.4f} mm")
    print(f"    net tilt {math.degrees(2*math.acos(min(1.0, abs(float(np.dot(q0,q1)))))):.4f} deg")
    zs = [r["position_m"][2] for r in rows]
    print(f"    origin z {min(zs):.6f} .. {max(zs):.6f}")

print("\n=== 5. penetration: minimum signed distance over the contact set ===")
mind = {}
n = 0
with (RUN / "contacts.jsonl").open("r", encoding="utf-8") as h:
    for line in h:
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        n += 1
        k = "|".join(r["pair"])
        d = r["signed_distance_m"]
        if k not in mind or d < mind[k]:
            mind[k] = d
print(f"  {n} contact rows")
for k, d in sorted(mind.items(), key=lambda kv: kv[1]):
    print(f"    {k:44s} min signed distance {d*1000:+.6f} mm")

print("\n=== 6. nobody is left below the floor ===")
worst = min(min(r["position_m"][2] for r in rr) for rr in traj.values())
print(f"  worst origin z over every body and frame: {worst:+.6f} m  "
      f"(threshold -1.0 m) -> {'PASS' if worst > -1.0 else 'FAIL'}")
for name, rr in traj.items():
    zs = [r["position_m"][2] for r in rr]
    print(f"    {name:18s} {min(zs):+10.6f} .. {max(zs):+10.6f}")

print("\n" + "=" * 100)
ok = (val["pass"] and worst > -1.0
      and cause.get(target, {}).get("moved")
      and not cause.get(target, {}).get("moved_without_preceding_contact"))
print(f"RESULT: {'CONSISTENT' if ok else 'INCONSISTENT - see above'}")
