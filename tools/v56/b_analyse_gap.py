"""Analyse the fine gap sweep: which settings fail, and is the failure physical or numerical?

The sweep found that all three assets reliably topple a following box over a broad gap range, but
that at SMALL gaps two of them topple under only 6 of 9 settings. That partial reliability needs a
cause. Two candidate explanations, distinguishable from the recorded numbers:

  * TRIGGER-limited: the striker only just reaches its balance point, so a weaker push leaves it
    short. Then the failing settings should be exactly the low-omega0 ones.
  * FRICTION/density-limited: the striker slides instead of pivoting when friction is low or the
    mass is high. Then the failing settings should correlate with density instead.

The `all_settings` records carry omega0 and density per run, so the failures can be attributed by
inspection. Also reports each asset's jam threshold in absolute millimetres.
"""

from __future__ import annotations

import json
from pathlib import Path

TMP = Path(r"D:\workspace\project1_database\tmp")
d = json.loads((TMP / "b_gap_sweep.json").read_text(encoding="utf-8"))

print("=" * 110)
print("WHICH SETTINGS FAIL AT THE SMALL GAPS? (target not toppled)")
for aid, rec in d["assets"].items():
    print(f"\n{aid}")
    print(f"  reliable range (all 9 settings)  : "
          f"{rec['reliable_gap_range_fraction']}")
    print(f"  requested gaps reliable          : {rec['reliable_at_requested_gaps']}")
    failures = []
    for g in rec["per_gap"]:
        bad = [r for r in g["all_settings"] if not r["target_toppled"]]
        if not bad:
            continue
        for r in bad:
            failures.append((g["gap_fraction"], r["gap_over_striker_thickness"],
                             r["omega0_rad_s"], r["density_kg_m3"],
                             r["striker_max_tilt_deg"], r["striker_toppled"],
                             r["contact_made"], r["target_max_tilt_deg"]))
    if not failures:
        print("  no failures at any gap / setting")
        continue
    print(f"  {'gap':>5s} {'g/t':>6s} {'omega0':>7s} {'dens':>6s} {'A_tip':>7s} {'A_topl':>6s} "
          f"{'contact':>7s} {'B_tip':>7s}")
    for f in failures:
        print(f"  {f[0]:5.2f} {f[1]:6.3f} {f[2]:7.2f} {f[3]:6.1f} {f[4]:7.2f} {str(f[5]):>6s} "
              f"{str(f[6]):>7s} {f[7]:7.2f}")
    om = sorted({f[2] for f in failures})
    de = sorted({f[3] for f in failures})
    print(f"  -> failing omega0 values  : {om}")
    print(f"  -> failing densities      : {de}")
    print(f"  -> failing gaps (fraction): {sorted({f[0] for f in failures})}")

print("\n" + "=" * 110)
print("JAM THRESHOLD in absolute terms")
print(f"  {'asset':42s} {'t_mm':>8s} {'h_mm':>8s} {'first_gap_toppling_mm':>22s} "
      f"{'as x own thickness':>19s}")
for aid, rec in d["assets"].items():
    spec = rec["spec"]
    t, h = spec["thickness_m"], spec["height_m"]
    first = None
    for g in rec["per_gap"]:
        if g["primary"]["target_toppled"]:
            first = g
            break
    if first:
        print(f"  {aid:42s} {t*1000:8.2f} {h*1000:8.2f} {first['gap_m']*1000:22.2f} "
              f"{first['gap_over_striker_thickness']:19.3f}")

print("\n" + "=" * 110)
print("FREE TOPPLE (no target) vs WITH TARGET -- does the target ever PREVENT toppling?")
for aid, rec in d["assets"].items():
    print(f"\n{aid}")
    for f in rec["free_topple"]:
        print(f"  free:  w={f['omega0_rad_s']:.1f} -> max_tilt {f['max_tilt_deg']:6.2f} "
              f"t_tip {f['topple_time_s']}  toppled={f['toppled']}")
    # At the smallest gap, compare with the free case at the same omega.
    g0 = rec["per_gap"][0]
    prim = g0["primary"]
    print(f"  at gap {g0['gap_fraction']:.2f} (w={prim['omega0_rad_s']:.1f}): max_tilt "
          f"{prim['striker_max_tilt_deg']:6.2f} toppled={prim['striker_toppled']} "
          f"contact={prim['contact_made']}")

print("\n" + "=" * 110)
print("TARGET TO PPLE TIME and TRANSLATION at the requested gaps (w=3.0, density=200)")
print(f"  {'asset':42s} {'gap':>5s} {'t_contact':>10s} {'t_B_topple':>11s} {'B_dx_mm':>9s}")
for aid, rec in d["assets"].items():
    for g in rec["per_gap"]:
        if g["gap_fraction"] in (0.15, 0.25, 0.35):
            p = g["primary"]
            print(f"  {aid:42s} {g['gap_fraction']:5.2f} {str(p['first_contact_time_s']):>10s} "
                  f"{str(p['target_topple_time_s']):>11s} "
                  f"{p['target_translation_x_m']*1000:9.2f}")
