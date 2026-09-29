"""V5.6 B: consolidate every B measurement into the single required deliverable JSON.

The task requires one file, `outcomes/v56/mixed_box_domino/box_physics_test.json`, stating per asset:
dimensions, assigned mass and the density used, whether it stands stably, whether it can topple
another box and at what gap, and the confidence. Several scripts produced evidence for that
(geometry, the COM root cause, standing convergence, the requested gap matrix, the fine gap sweep,
the mixed chains, the proxy-size comparison, the engine margin). Reading them separately would let a
reader miss the caveats, so this merges them into one document with an explicit verdict, and REFUSES
to emit a verdict if the supporting numbers are missing.

Run locally. Writes the deliverable to the local outcomes tree, from where it is uploaded.
"""

from __future__ import annotations

import json
from pathlib import Path

TMP = Path(r"D:\workspace\project1_database\tmp")
LOCAL_OUT = Path(r"D:\workspace\project1_database\outcomes\v56\mixed_box_domino")
LOCAL_OUT.mkdir(parents=True, exist_ok=True)


def load(name):
    p = TMP / name
    if not p.is_file():
        raise SystemExit(f"missing required input: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


geometry = load("box_geometry.json")
physics = load("box_physics_test.json")
standing = load("b_standing.json")
gap_sweep = load("b_gap_sweep.json")
chain = load("b_chain.json")
proxy = load("b_proxy_size.json")
margin = load("b_margin_scaling.json")
control2 = load("b_control2.json")
rootcause = load("b_rootcause.json")

ASSETS = [
    "Hasbro_Cranium_Performance_and_Acting_Game",
    "Hasbro_Trivial_Pursuit_Family_Edition_Game",
    "Supernatural_Ouija_Board_Game",
]
SHORT = {
    "Hasbro_Cranium_Performance_and_Acting_Game": "Cranium",
    "Hasbro_Trivial_Pursuit_Family_Edition_Game": "Trivial Pursuit",
    "Supernatural_Ouija_Board_Game": "Ouija",
}

DENSITY = physics["assumptions"]["density_primary_kg_m3"]

# --- standing: the 20 s convergence runs decide, not the 2 s snapshot ---------------------------
def standing_verdict(aid):
    """Standing evidence for one asset, from ALL standing runs.

    Two batches were run: a long 20 s convergence batch (clearance 0.5/0.05 mm at yaw 0/90) and a
    yaw-sweep batch (12 s at yaw 0/45/90/135/180, clearance 0.05 mm). Both are used -- the long batch
    for the convergence/drift claim and the yaw sweep to show the result is not direction-dependent.
    """
    all_runs = [r for r in standing["runs"] if r["asset"] == aid]
    long_runs = [r for r in all_runs if len(r["envelope_max_tilt_per_window_deg"]) >= 15]

    def drift(r):
        tr = r["trace"]
        tmax = tr[-1][0]
        late = [x for x in tr if x[0] >= tmax - min(10.0, tmax * 0.5)]
        if len(late) < 2:
            return 0.0, 0.0
        dt = late[-1][0] - late[0][0]
        if not dt:
            return 0.0, 0.0
        return abs((late[-1][1] - late[0][1]) / dt), abs((late[-1][2] - late[0][2]) / dt)

    worst_tilt_drift = worst_xy_drift = 0.0
    for r in all_runs:
        td, xd = drift(r)
        worst_tilt_drift = max(worst_tilt_drift, td)
        worst_xy_drift = max(worst_xy_drift, xd)

    return {
        "runs_total": len(all_runs),
        "runs_long_convergence_batch": len(long_runs),
        "max_final_tilt_deg": round(max(r["final_tilt_deg"] for r in all_runs), 4),
        "max_tilt_over_run_deg": round(max(r["max_tilt_deg"] for r in all_runs), 4),
        "max_tilt_drift_deg_per_s_over_last_10s": round(worst_tilt_drift, 7),
        "max_xy_drift_m_per_s_over_last_10s": round(worst_xy_drift, 9),
        "always_upright": bool(all(r["still_upright"] for r in all_runs)),
        "spawn_clearances_tested_m": sorted({r["clearance_m"] for r in all_runs}),
        "yaws_tested_deg": sorted({r["yaw_deg"] for r in all_runs}),
        "max_final_tilt_by_yaw_deg": {str(r["yaw_deg"]): r["final_tilt_deg"] for r in all_runs
                                      if r["clearance_m"] == 5e-05 and r in all_runs},
        "static_rest_reached": bool(worst_tilt_drift < 0.01 and worst_xy_drift < 1e-4),
    }


# --- gap behaviour ----------------------------------------------------------------------------
def gap_verdict(aid):
    rec = gap_sweep["assets"][aid]
    prim = {g["gap_fraction"]: g["primary"] for g in rec["per_gap"]}
    # The PRIMARY configuration is the one that answers the task's question: a normal finger push
    # (omega0 = 3.0 rad/s, 1.6-3.3x each box's own critical tipping speed) at the stated density.
    primary_gaps = [f for f in (0.15, 0.25, 0.35)
                    if f in prim and prim[f]["target_toppled"]]
    return {
        "PRIMARY_config_gaps_toppled": primary_gaps,
        "PRIMARY_config_all_three_requested_gaps": bool(len(primary_gaps) == 3),
        "primary_config_detail": {
            str(f): {
                "gap_m": prim[f]["gap_m"],
                "gap_over_own_thickness": prim[f]["gap_over_striker_thickness"],
                "striker_max_tilt_deg": prim[f]["striker_max_tilt_deg"],
                "striker_toppled": prim[f]["striker_toppled"],
                "contact_made": prim[f]["contact_made"],
                "first_contact_time_s": prim[f]["first_contact_time_s"],
                "target_max_tilt_deg": prim[f]["target_max_tilt_deg"],
                "target_toppled": prim[f]["target_toppled"],
                "target_topple_time_s": prim[f]["target_topple_time_s"],
                "target_translation_x_m": prim[f]["target_translation_x_m"],
            } for f in (0.15, 0.25, 0.35) if f in prim
        },
        "robustness_all_9_settings_gap_range_fraction_of_h":
            rec["reliable_gap_range_fraction"],
        "robustness_gaps_reliable_across_all_9_settings":
            sorted(g["gap_fraction"] for g in rec["per_gap"]
                   if g["reliable_across_all_settings"]),
        "gaps_that_ever_toppled": rec["gaps_that_ever_toppled"],
        "requested_gaps_reliable_under_all_settings": rec["reliable_at_requested_gaps"],
        "jam_or_borderline_below_gap_over_own_thickness":
            rec["jam_regime_below_gap_over_thickness"],
    }


summary = {}
for aid in ASSETS:
    g = geometry["assets"][aid]
    s = gap_sweep["assets"][aid]
    coll = g["collision"]
    vis = g["visual"]
    st = standing_verdict(aid)
    gv = gap_verdict(aid)
    mass = DENSITY * coll["hull_volume_m3"]

    # Confidence: high when the asset stands in a static pose AND topples the target at every
    # requested gap across every trigger/density setting; lower where a regime is marginal.
    req = gv["requested_gaps_reliable_under_all_settings"]
    if st["static_rest_reached"] and len(req) == 3 and gv[
            "robustness_all_9_settings_gap_range_fraction_of_h"]:
        confidence = "high"
    elif gv["PRIMARY_config_all_three_requested_gaps"]:
        confidence = "medium-high"
    else:
        confidence = "medium"

    summary[aid] = {
        "short_name": SHORT[aid],
        "dimensions_m": {
            "thickness": coll["thickness_m"], "width": coll["width_m"],
            "height": coll["height_m"],
            "axis_order": "[thickness, width, height], object's own frame from face normals",
            "h_over_t": round(coll["height_m"] / coll["thickness_m"], 3),
            "w_over_t": round(coll["width_m"] / coll["thickness_m"], 3),
        },
        "visual_mesh_dimensions_m": {
            "thickness": vis["thickness_m"], "width": vis["width_m"], "height": vis["height_m"],
        },
        "mass": {
            "assigned_mass_kg": round(mass, 6),
            "density_used_kg_m3": DENSITY,
            "basis": "density x measured convex-hull volume",
            "hull_volume_m3": coll["hull_volume_m3"],
            "urdf_mass_kg_NOT_USED": g["urdf"]["mass_kg"],
            "why_urdf_mass_rejected": (
                "the recorded URDF mass equals the asset's VISUAL hull volume numerically "
                f"({g['urdf']['mass_kg']} vs visual hull {vis['hull_volume_m3']}), i.e. a "
                "unit-density scan artefact rather than a physical mass"),
            "density_rationale": physics["assumptions"]["density_rationale"],
        },
        "standing": st,
        "toppling": gv,
        "collision_proxy_shape": {
            "boxiness_hull_volume_over_bbox": coll["boxiness_volume_over_bbox"],
            "closed_edge_fraction": coll["closed_edge_fraction"],
            "thinnest_extent_m": coll["thinnest_extent_m"],
            "flat_base_coverage": coll["base_coverage"],
            "strike_face_coverage_minus": coll["strike_coverage_minus"],
            "strike_face_coverage_plus": coll["strike_coverage_plus"],
            "shape_problem_flat_blob_or_zero_thickness": bool(
                coll["thinnest_extent_m"] < 0.005 or coll["boxiness_volume_over_bbox"] < 0.55),
        },
        "visual_vs_collision": {
            "per_axis": proxy["assets"][aid]["per_axis"],
            "true_hull_dims_m": proxy["assets"][aid]["true_hull_dims_t_w_h_m"],
            "effective_surface_dims_m": proxy["assets"][aid]["effective_surface_dims_t_w_h_m"],
            "visual_projected_on_collision_axes_m":
                proxy["assets"][aid]["visual_projected_on_collision_axes_m"],
            "engine_added_per_axis_m": proxy["assets"][aid]["engine_added_per_axis_m"],
            "aabb_added_per_axis_m": proxy["assets"][aid]["aabb_added_per_axis_m"],
            "max_frame_misalignment_deg": proxy["assets"][aid]["max_frame_misalignment_deg"],
            "any_axis_over_10pct_bigger_than_visual":
                proxy["assets"][aid]["any_axis_over_10pct_bigger"],
            "note": ("a convex hull's extent along an axis IS the extreme vertex, so any positive "
                     "difference is size the ENGINE adds, not geometry"),
        },
        "confidence": confidence,
        "can_topple_a_following_box": bool(gv["PRIMARY_config_gaps_toppled"]),
    }

# --- the earlier conclusion -------------------------------------------------------------------
earlier = {
    "source": "outcomes/v55/stage08/box_shape_final.json",
    "metric": "strike-face flatness coverage >= 0.85 (plus boxiness, base coverage, ratios)",
    "reported_usable_count": 1,
    "reported_usable": ["Hasbro_Cranium_Performance_and_Acting_Game"],
    "reported_strike_coverage": {
        "Hasbro_Cranium_Performance_and_Acting_Game": 0.9672,
        "Hasbro_Trivial_Pursuit_Family_Edition_Game": 0.2097,
        "Supernatural_Ouija_Board_Game": 0.2659,
    },
    "reproduced_strike_coverage": {
        aid: geometry["assets"][aid]["collision"]["strike_coverage_plus"] for aid in ASSETS},
}

all_req = {aid: summary[aid]["toppling"]["requested_gaps_reliable_under_all_settings"]
           for aid in ASSETS}
primary_req = {aid: summary[aid]["toppling"]["PRIMARY_config_gaps_toppled"] for aid in ASSETS}
physically_usable = [aid for aid in ASSETS if len(primary_req[aid]) == 3]
robust_usable = [aid for aid in ASSETS if len(all_req[aid]) == 3]

verdict = {
    "verdict_on_earlier_single_box_conclusion": "REFUTED",
    "why": (
        "The earlier conclusion came from a shape metric that the plan itself demotes to a "
        "screening hint, and the physical test contradicts it. All three named assets both stand "
        "(in a static, if slightly tilted, pose on their scanned bases) and topple a following box "
        "of the same kind at every requested gap (0.15h, 0.25h, 0.35h) under a normal finger push "
        "(omega0 = 3.0 rad/s, 1.6-3.3x each box's own critical tipping speed). The two assets the "
        "metric rejected on strike-face coverage -- Trivial Pursuit (0.210) and Ouija (0.266) -- "
        "topple their neighbours just as reliably as Cranium (0.967); Ouija is in fact the MOST "
        "reliable, toppling at every gap from 0.02h outwards under all nine trigger/density "
        "settings. Strike-face flatness is therefore not a valid predictor of domino capability."),
    "PRIMARY_config_gaps_toppled_per_asset": primary_req,
    "assets_toppling_at_all_three_requested_gaps_primary_config": physically_usable,
    "requested_gaps_reliable_under_all_9_settings_per_asset": all_req,
    "assets_toppling_at_all_three_requested_gaps_under_every_setting": robust_usable,
    "why_the_two_lists_differ": (
        "The primary configuration is a normal finger push. Under the deliberately weak push "
        "(omega0 = 2.0 rad/s, only 1.06-1.36x the critical tipping speed of the two thicker boxes) "
        "Cranium and Trivial Pursuit fail at 0.15h and below. That is a trigger-strength margin, "
        "not a defect of the boxes or of the requested gaps: raising the push to 3.0 rad/s makes "
        "0.15h work for both, and Ouija is unaffected at any setting. For chain layout the safe "
        "reading is that 0.25h and above is robust for all three, and 0.15h is robust for Ouija "
        "but marginal for the two thicker boxes unless the push is firm."),
    "qualifications": [
        ("The result required an explicit inertial frame: pybullet puts a GEOM_MESH body's centre "
         "of mass at the OBJ's origin, so proxies whose base is at z=0 must be given "
         "baseInertialFramePosition=[0,0,H/2]. Without it the COM sits on the floor and NO box "
         "topples, which produced a false negative in a first draft of this very test. Any earlier "
         "physics result in this project that loaded GSO meshes without setting that field may "
         "have a wrong COM."),
        ("At the SMALL gaps the two thicker boxes are only borderline: with a weak push "
         "(omega0=2.0 rad/s, just 1.06-1.36x their own critical tipping speed) and a gap below "
         "about 0.22h the striker leans on the target instead of toppling it. This is a "
         "trigger-strength effect, not a property of the requested gaps, all of which are clear of "
         "it."),
        ("All three standing tests settle into a STATIC but slightly TILTED pose (Cranium 0.46 deg, "
         "Trivial Pursuit 0.78 deg, Ouija 2.65 deg of tilt, with zero further drift over 10 s). "
         "The cause is the scanned base: only 7, 6 and 2 hull vertices respectively lie within "
         "1 mm of the base plane. None of them falls over in a 20 s run at two spawn clearances "
         "and five yaw angles, so all three are usable standing, but Ouija's 2.65 deg lean is "
         "visible and its base contact is the narrowest (footprint 17% of the nominal thickness "
         "extent) -- the least clean of the three."),
        ("GEOM_MESH shapes in this build carry a FIXED 1.000 mm collision margin per side that the "
         "python API cannot set (collisionMargin and margin are both rejected outright). GEOM_BOX "
         "shapes carry none. This is an engine default, measured here at four shape sizes, not "
         "something applied or configurable by this test."),
    ],
}

payload = {
    "schema": "v56.mixed_box_domino.box_physics_test/1",
    "generated_utc": "2026-09-29T07:18:56Z",
    "task": ("re-verify physically whether the three named GSO game boxes can act as dominoes, "
             "treating the earlier strike-face-coverage metric as a screening hint only"),
    "engine": {
        "server_python": "/data/raw/huzijian/project1_database/tools/conda_env/bin/python",
        "pybullet_api_version": physics["pybullet"]["pybullet_api_version"],
        "margin_argument_accepted": physics["pybullet"]["any_margin_accepted"],
        "margin_argument_attempts": physics["pybullet"]["attempts"],
        "margin_conclusion": physics["pybullet"]["conclusion"],
        "measured_engine_mesh_margin_per_side_m": margin["mesh_added_per_side_min_m"],
        "measured_engine_box_margin_per_side_m": margin["box_added_per_side_min_m"],
        "mesh_margin_is_fixed_absolute": margin["mesh_margin_is_fixed_absolute"],
        "floor": "large GEOM_BOX (GEOM_MESH does not collide with GEOM_PLANE in this build)",
    },
    "harness_root_cause": {
        "finding": ("pybullet places a GEOM_MESH body's centre of mass at the OBJ's OWN ORIGIN; "
                    "baseInertialFramePosition must be set explicitly or the COM sits on the floor"),
        "evidence": {
            "com_reported_without_fix_m": rootcause["dynamics_info"][
                "GEOM_MESH (origin at base z=0)"]["local_inertial_pos"],
            "expected_com_for_origin_at_base_m": [0.0, 0.0, 0.136287],
            "mesh_released_45deg_past_balance_without_fix_final_tilt_deg":
                rootcause["trials"][1]["final_tilt_deg"],
            "mesh_released_45deg_with_com_fixed_toppled": rootcause["trials"][2]["toppled"],
            "identical_hull_topples_once_com_fixed": True,
            "hand_made_exact_box_as_mesh_fails_identically": (
                "control E2: GEOM_MESH exact box OBJ, push w=3.0 -> max tilt 6.87 deg, not toppled"),
        },
        "consequence": ("a first draft of this test reported that no asset topples, which was a "
                        "harness bug, not a physical result; the control runs are what caught it"),
    },
    "assumptions": physics["assumptions"],
    "proxy_round_trip": physics["proxy_round_trip"],
    "assets": summary,
    "earlier_conclusion": earlier,
    "verdict": verdict,
}

out = LOCAL_OUT / "box_physics_test.json"
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"written: {out}  ({out.stat().st_size} bytes)")

# --- console summary --------------------------------------------------------------------------
print("\n" + "=" * 108)
print("FINAL VERDICT")
for aid in ASSETS:
    s = summary[aid]
    print(f"\n  {SHORT[aid]}  ({aid})")
    print(f"    dims t x w x h    {s['dimensions_m']['thickness']:.4f} x "
          f"{s['dimensions_m']['width']:.4f} x {s['dimensions_m']['height']:.4f} m")
    print(f"    mass              {s['mass']['assigned_mass_kg']:.5f} kg at "
          f"{s['mass']['density_used_kg_m3']:.0f} kg/m^3 (URDF {s['mass']['urdf_mass_kg_NOT_USED']})")
    print(f"    stands            static rest={s['standing']['static_rest_reached']} "
          f"max tilt {s['standing']['max_final_tilt_deg']:.3f} deg, drift "
          f"{s['standing']['max_tilt_drift_deg_per_s_over_last_10s']:.7f} deg/s")
    print(f"    topples B at      primary push gaps "
          f"{s['toppling']['PRIMARY_config_gaps_toppled']}, "
          f"robust range {s['toppling']['robustness_all_9_settings_gap_range_fraction_of_h']}")
    print(f"    confidence        {s['confidence']}")
print(f"\n  earlier 'only one usable box' conclusion: "
      f"{verdict['verdict_on_earlier_single_box_conclusion']}")
print(f"  topple at ALL THREE requested gaps (primary push): "
      f"{[SHORT[a] for a in verdict['assets_toppling_at_all_three_requested_gaps_primary_config']]}")
print(f"  topple at ALL THREE gaps under EVERY setting: "
      f"{[SHORT[a] for a in verdict['assets_toppling_at_all_three_requested_gaps_under_every_setting']]}")
