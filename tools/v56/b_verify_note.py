"""Verify every number quoted in the B note against the delivered JSON, so the note cannot drift.

The note is prose read by humans; the JSON is the record. If a figure in the note disagrees with the
JSON, that is a reporting bug of exactly the kind this re-verification exists to catch. This checks
the load-bearing claims mechanically.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(r"D:\workspace\project1_database\outcomes\v56\mixed_box_domino")
d = json.loads((OUT / "box_physics_test.json").read_text(encoding="utf-8"))

checks = []


def check(label, got, want, tol=1e-6):
    if isinstance(want, float):
        ok = abs(got - want) <= tol
    else:
        ok = got == want
    checks.append((ok, label, got, want))


A = d["assets"]
CRAN = "Hasbro_Cranium_Performance_and_Acting_Game"
TRIV = "Hasbro_Trivial_Pursuit_Family_Edition_Game"
OUIJ = "Supernatural_Ouija_Board_Game"

# §1 dims and masses
check("Cranium thickness mm", round(A[CRAN]["dimensions_m"]["thickness"] * 1000, 3), 55.838, 1e-3)
check("Trivial thickness mm", round(A[TRIV]["dimensions_m"]["thickness"] * 1000, 3), 73.462, 1e-3)
check("Ouija height mm", round(A[OUIJ]["dimensions_m"]["height"] * 1000, 3), 408.406, 1e-3)
check("Cranium mass kg", round(A[CRAN]["mass"]["assigned_mass_kg"], 4), 0.6249, 1e-4)
check("Trivial mass kg", round(A[TRIV]["mass"]["assigned_mass_kg"], 4), 0.7059, 1e-4)
check("Ouija mass kg", round(A[OUIJ]["mass"]["assigned_mass_kg"], 4), 1.2510, 1e-4)
check("density", A[CRAN]["mass"]["density_used_kg_m3"], 200.0, 1e-9)

# the URDF==visual-hull-volume claim
for aid, urdf in ((CRAN, 0.0028040457), (TRIV, 0.0032490056), (OUIJ, 0.0054948609)):
    got = A[aid]["mass"]["urdf_mass_kg_NOT_USED"]
    check(f"{aid[:12]} urdf mass == visual hull vol", round(got, 10), urdf, 1e-9)

# §2 standing
check("Cranium static rest", A[CRAN]["standing"]["static_rest_reached"], True)
check("Cranium tilt", round(A[CRAN]["standing"]["max_final_tilt_deg"], 2), 0.46, 0.005)
check("Trivial tilt", round(A[TRIV]["standing"]["max_final_tilt_deg"], 2), 0.79, 0.005)
check("Ouija tilt", round(A[OUIJ]["standing"]["max_final_tilt_deg"], 2), 2.65, 0.005)
check("all always upright",
      all(A[a]["standing"]["always_upright"] for a in (CRAN, TRIV, OUIJ)), True)
check("clearances tested", A[OUIJ]["standing"]["spawn_clearances_tested_m"], [5e-05, 0.0005])
check("yaws tested", A[OUIJ]["standing"]["yaws_tested_deg"], [0.0, 45.0, 90.0, 135.0, 180.0])

# §3 primary-config gaps
for aid in (CRAN, TRIV, OUIJ):
    check(f"{aid[:12]} primary gaps", A[aid]["toppling"]["PRIMARY_config_gaps_toppled"],
          [0.15, 0.25, 0.35])
    check(f"{aid[:12]} topples at all 3", A[aid]["toppling"]["PRIMARY_config_all_three_requested_gaps"],
          True)

check("Cranium 0.15h gap mm", round(A[CRAN]["toppling"]["primary_config_detail"]["0.15"]["gap_m"] * 1000, 1), 40.9, 0.05)
check("Ouija 0.35h gap mm", round(A[OUIJ]["toppling"]["primary_config_detail"]["0.35"]["gap_m"] * 1000, 1), 142.9, 0.05)
check("Cranium 0.15h B tilt", round(A[CRAN]["toppling"]["primary_config_detail"]["0.15"]["target_max_tilt_deg"], 1), 90.8, 0.05)
check("Trivial 0.15h B tilt", round(A[TRIV]["toppling"]["primary_config_detail"]["0.15"]["target_max_tilt_deg"], 1), 91.4, 0.05)
check("Cranium 0.25h B dx mm", round(A[CRAN]["toppling"]["primary_config_detail"]["0.25"]["target_translation_x_m"] * 1000, 1), 181.0, 0.05)

# §3 reliable ranges
check("Cranium robust range", A[CRAN]["toppling"]["robustness_all_9_settings_gap_range_fraction_of_h"], [0.25, 0.7])
check("Trivial robust range", A[TRIV]["toppling"]["robustness_all_9_settings_gap_range_fraction_of_h"], [0.25, 0.7])
check("Ouija robust range", A[OUIJ]["toppling"]["robustness_all_9_settings_gap_range_fraction_of_h"], [0.02, 0.7])

# §6 visual vs collision (true hull extent vs visual extent, on the collision's own axes)
for aid, rels in ((CRAN, [1.79, 0.58, 0.67]), (TRIV, [3.79, 1.11, 0.67]),
                  (OUIJ, [4.05, 1.18, 0.52])):
    rows = A[aid]["visual_vs_collision"]["per_axis"]
    for r, want in zip(rows, rels):
        got = (r["collision_true_extent_m"] - r["visual_extent_m"]) / r["visual_extent_m"] * 100
        check(f"{aid[:12]} {r['axis_role']} rel %", round(got, 2), want, 0.02)

check("engine mesh margin m", d["engine"]["measured_engine_mesh_margin_per_side_m"], 0.001, 1e-9)
check("engine box margin m", d["engine"]["measured_engine_box_margin_per_side_m"], 0.0, 1e-9)
check("margin arg rejected", d["engine"]["margin_argument_accepted"], False)

# §7 COM finding
check("COM reported without fix", d["harness_root_cause"]["evidence"][
    "com_reported_without_fix_m"], [0.0, 0.0, 0.0])
check("mesh without fix sprang back deg", d["harness_root_cause"]["evidence"][
    "mesh_released_45deg_past_balance_without_fix_final_tilt_deg"], 0.46, 0.01)
check("mesh with fix toppled", d["harness_root_cause"]["evidence"][
    "mesh_released_45deg_with_com_fixed_toppled"], True)

# verdict
check("verdict", d["verdict"]["verdict_on_earlier_single_box_conclusion"], "REFUTED")

bad = [c for c in checks if not c[0]]
for ok, label, got, want in checks:
    print(f"  [{'OK ' if ok else 'BAD'}] {label:44s} got={got} want={want}")
print(f"\n{len(checks) - len(bad)}/{len(checks)} checks passed")
if bad:
    raise SystemExit(f"{len(bad)} MISMATCHES between note and JSON: {[b[1] for b in bad]}")
print("every quoted figure in the note agrees with the delivered JSON")
