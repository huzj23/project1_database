"""Analyse the B results locally: standing convergence, and what the failures actually mean.

Two questions the raw logs cannot settle by eye, both answered from the downloaded JSON:

  1. STANDING. The first 2 s test flagged Trivial Pursuit and Ouija as "not at rest". The 20 s runs
     show a FIXED final tilt with an essentially zero velocity -- i.e. the box has settled into a
     static tilted pose on a warped base, not kept rocking. This computes, for every standing run,
     the tilt drift rate over the last 10 s and the drift rate of the xy position, so "static tilted
     rest" is distinguished from "slowly falling" by a number.
  2. THE 0.02h CONTROL. All three assets toppled B at 0.15h-0.35h but the 0.02h control showed the
     striker NOT toppling for two assets. That is counter-intuitive and needs explaining from the
     recorded numbers rather than hand-waving: at 0.02h the two boxes start almost touching, so the
     striker cannot rotate before it is already jammed against the target.

Read-only over the downloaded JSON in `tmp/`.
"""

from __future__ import annotations

import json
from pathlib import Path

TMP = Path(r"D:\workspace\project1_database\tmp")

stand = json.loads((TMP / "b_standing.json").read_text(encoding="utf-8"))
phys = json.loads((TMP / "box_physics_test.json").read_text(encoding="utf-8"))

print("=" * 108)
print("1. STANDING: is the box at a STATIC tilted rest, or still moving?")
print("   (drift rate over the last 10 s of a 20 s run; a static pose gives ~0 per second)")
print(f"\n  {'asset':44s} {'clear':>6s} {'yaw':>5s} {'finalTilt':>10s} {'tiltDrift':>11s} "
      f"{'xyDrift':>10s} {'verdict':>22s}")
# The runs list holds two batches; keep the long 20 s ones (they carry the full envelope).
long_runs = [r for r in stand["runs"] if len(r["envelope_max_tilt_per_window_deg"]) >= 15]
rows = []
for aid in stand["spec"]:
    for r in long_runs:
        if r["asset"] != aid:
            continue
        tr = r["trace"]
        # trace rows are [t, tilt, drift]; use the last 10 s of samples
        tmax = tr[-1][0]
        late = [x for x in tr if x[0] >= tmax - 10.0]
        if len(late) < 2:
            continue
        dt = late[-1][0] - late[0][0]
        tilt_drift = (late[-1][1] - late[0][1]) / dt if dt else 0.0
        xy_drift = (late[-1][2] - late[0][2]) / dt if dt else 0.0
        # A static tilted rest: tilt change per second tiny, xy creep tiny.
        if abs(tilt_drift) < 0.01 and abs(xy_drift) < 1e-4 and r["still_upright"]:
            verdict = "static tilted rest"
        elif not r["still_upright"]:
            verdict = "FELL OVER"
        else:
            verdict = "STILL MOVING"
        rows.append((aid, r, tilt_drift, xy_drift, verdict))
        print(f"  {aid:44s} {r['clearance_m']*1000:5.2f}m {r['yaw_deg']:5.0f} "
              f"{r['final_tilt_deg']:10.5f} {tilt_drift:11.7f} {xy_drift:10.4e} {verdict:>22s}")

print(f"\n  summary over {len(rows)} long runs:")
for aid in stand["spec"]:
    sub = [r for r in rows if r[0] == aid]
    worst = max(abs(r[2]) for r in sub) if sub else 0.0
    print(f"    {aid:44s} max |tilt drift| {worst:.7f} deg/s  "
          f"all upright {all(r[1]['still_upright'] for r in sub)}  "
          f"max final tilt {max(r[1]['final_tilt_deg'] for r in sub):.4f} deg")

print("\n" + "=" * 108)
print("2. WHY did the 0.02h control fail for two assets while 0.15-0.35h worked?")
print("   (gap_m vs the striker's own thickness -- at 0.02h there is no room to rotate)")
for aid, s in phys["summary"].items():
    t = s["dims_m_t_w_h"][0]
    h = s["dims_m_t_w_h"][2]
    print(f"\n  {aid}")
    print(f"    striker thickness {t*1000:.2f} mm, height {h*1000:.2f} mm")
    for c in phys["cases"]:
        if c.get("case") == "two_box_reach_control" and c.get("striker") == aid:
            print(f"    0.02h control: gap {c['gap_m']*1000:.2f} mm (= {c['gap_m']/t:.3f} x own "
                  f"thickness)  A_max_tilt {c['striker_max_tilt_deg']:.2f}  "
                  f"A_toppled {c['striker_toppled']}  contact {c['contact_between_a_and_b_made']}  "
                  f"B_toppled {c['target_toppled']}")
    for c in phys["cases"]:
        if c.get("case") == "two_box" and c.get("striker") == aid:
            print(f"    {c['gap_fraction_of_shorter_height']:.2f}h: gap {c['gap_m']*1000:7.2f} mm "
                  f"(= {c['gap_m']/t:.3f} x own thickness)  A_max_tilt "
                  f"{c['striker_max_tilt_deg']:7.2f}  A_toppled {str(c['striker_toppled']):>5s}  "
                  f"contact {str(c['contact_between_a_and_b_made']):>5s}  "
                  f"B_toppled {str(c['target_toppled']):>5s}")

print("\n" + "=" * 108)
print("3. CROSS-PAIR summary at 0.25h (all ordered pairs)")
for c in phys["cases"]:
    if c.get("case") == "two_box_cross":
        print(f"  {c['striker'][:38]:38s} -> {c['target'][:38]:38s} "
              f"massA {c['striker_mass_kg']:.4f} massB {c['target_mass_kg']:.4f}  "
              f"A_topl {str(c['striker_toppled']):>5s} contact {str(c['contact_between_a_and_b_made']):>5s} "
              f"B_topl {str(c['target_toppled']):>5s} B_tip {c['target_max_tilt_deg']:7.2f}")

print("\n" + "=" * 108)
print("4. VISUAL vs COLLISION proxy size (does the hull exceed the visual?)")
geo = json.loads((TMP / "box_geometry.json").read_text(encoding="utf-8"))
print(f"  {'asset':44s} {'axis':14s} {'coll_mm':>9s} {'vis_mm':>9s} {'diff_mm':>9s} {'rel%':>8s}")
for aid, rec in geo["assets"].items():
    for r in rec.get("collision_vs_visual_in_collision_frame", []):
        print(f"  {aid:44s} {r['axis_role']:14s} {r['collision_extent_m']*1000:9.3f} "
              f"{r['visual_extent_m']*1000:9.3f} {r['collision_minus_visual_m']*1000:9.3f} "
              f"{r['relative_difference']*100:8.3f}")
    print(f"  {'':44s} max relative growth "
          f"{rec['max_relative_growth']*100:.3f}%  bigger_on_any_axis="
          f"{rec['collision_bigger_on_any_axis']}")
