"""Final gate: confirm the uploaded deliverable on the server is complete and self-consistent.

Run on the server. Exits non-zero (and says why) if the delivered JSON is missing a required field,
disagrees with itself, or does not support the verdict it states. This is the check that the task's
"be rigorous" requirement lands on the actual artifact a reader will open.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

P = Path("/data/raw/huzijian/project1_database/outcomes/v56/mixed_box_domino/box_physics_test.json")
d = json.loads(P.read_text(encoding="utf-8"))

ASSETS = [
    "Hasbro_Cranium_Performance_and_Acting_Game",
    "Hasbro_Trivial_Pursuit_Family_Edition_Game",
    "Supernatural_Ouija_Board_Game",
]

problems = []

for key in ("schema", "engine", "harness_root_cause", "assumptions", "assets", "earlier_conclusion",
            "verdict"):
    if key not in d:
        problems.append(f"missing top-level key {key}")

print(f"schema  : {d.get('schema')}")
print(f"engine  : pybullet {d['engine']['pybullet_api_version']}, "
      f"margin accepted = {d['engine']['margin_argument_accepted']}, "
      f"mesh margin = {d['engine']['measured_engine_mesh_margin_per_side_m']} m")
print(f"verdict : {d['verdict']['verdict_on_earlier_single_box_conclusion']}")

for aid in ASSETS:
    if aid not in d["assets"]:
        problems.append(f"asset missing: {aid}")
        continue
    a = d["assets"][aid]
    # Required per the task: dimensions, assigned mass, density used, standing, toppling + gap,
    # confidence.
    dims = a["dimensions_m"]
    m = a["mass"]
    st = a["standing"]
    tp = a["toppling"]
    print(f"\n{aid}")
    print(f"  dims t/w/h      {dims['thickness']:.6f} x {dims['width']:.6f} x {dims['height']:.6f} m")
    print(f"  mass            {m['assigned_mass_kg']:.6f} kg at {m['density_used_kg_m3']} kg/m^3 "
          f"(urdf {m['urdf_mass_kg_NOT_USED']})")
    print(f"  stands          static_rest={st['static_rest_reached']} "
          f"max_tilt={st['max_final_tilt_deg']} deg drift={st['max_tilt_drift_deg_per_s_over_last_10s']} deg/s")
    print(f"  topples at      {tp['PRIMARY_config_gaps_toppled']} (primary push); "
          f"robust range {tp['robustness_all_9_settings_gap_range_fraction_of_h']}")
    print(f"  confidence      {a['confidence']}")

    if "density_used_kg_m3" not in m:
        problems.append(f"{aid}: no density recorded")
    if not st.get("static_rest_reached"):
        problems.append(f"{aid}: standing not resolved to a static rest")
    if not tp.get("PRIMARY_config_gaps_toppled"):
        problems.append(f"{aid}: primary config toppled no requested gap")
    for f in ("0.15", "0.25", "0.35"):
        det = tp["primary_config_detail"].get(f)
        if det is None:
            problems.append(f"{aid}: no detail for gap {f}")
        elif not det.get("target_toppled") and not det.get("contact_made"):
            problems.append(f"{aid}: gap {f} neither toppled nor contacted")

# The verdict must agree with the per-asset records.
all_primary = all(d["assets"][a]["toppling"]["PRIMARY_config_all_three_requested_gaps"]
                  for a in ASSETS)
stated = d["verdict"]["verdict_on_earlier_single_box_conclusion"]
print(f"\nall three assets topple at all three requested gaps (primary push): {all_primary}")
print(f"stated verdict: {stated}")
if all_primary and stated != "REFUTED":
    problems.append(f"verdict {stated!r} contradicts the measurements (all three work)")
if not all_primary and stated == "REFUTED":
    problems.append("verdict REFUTED but not all assets toppled at all requested gaps")

if d["engine"]["margin_argument_accepted"]:
    problems.append("margin was reported accepted, which contradicts the recorded API behaviour")

print("\n" + "=" * 90)
if problems:
    print(f"{len(problems)} PROBLEM(S):")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print("deliverable is complete and self-consistent")
