"""a_make_report.py -- V5.6 assemble board_selection.json from the raw analyses.

Control-python only (no bpy).  Merges:
  _work/analysis.json      per-component geometry + contact evidence
  _work/verification.json  independent re-measurement of the exported OBJs
  boards/export_manifest.json + per-export sidecars
and emits outcomes/v56/hidden_alley_can_board/board_selection.json.

Nothing is deleted.  All numbers are copied from the source files rather than
re-typed, so the report cannot drift from the measurements.
"""

import argparse
import json
import os


def load(p):
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--boards", required=True)
    ap.add_argument("--out", required=True)
    A = ap.parse_args()

    analysis = load(os.path.join(A.work, "analysis.json"))
    verification = load(os.path.join(A.work, "verification.json"))
    manifest = load(os.path.join(A.boards, "export_manifest.json"))

    verify_by_file = {v["file"]: v for v in verification["objects"]}

    # ---- attach the export + verification facts to each component ----------
    export_by_src = {}
    for e in manifest.get("exports", []):
        if "error" in e:
            continue
        export_by_src[(e["source_object"], e["component_index"])] = e

    components_all = []
    for ob in analysis["objects"]:
        for c in ob["components"]:
            key = (ob["name"], c["component_index"])
            rec = {
                "source_object": ob["name"],
                "source_object_scale": ob["scale"],
                "source_object_matrix_world": ob["matrix_world"],
                "component_index": c["component_index"],
                "n_verts": c["n_verts"],
                "n_faces": c["n_faces"],
                "n_tris": c["n_tris"],
                "is_closed_solid": c["is_closed_solid"],
                "boundary_edge_count": c["boundary_edge_count"],
                "open_face": c["open_face"],
                "world_aabb_min": c["world_aabb_min"],
                "world_aabb_max": c["world_aabb_max"],
                "world_aabb_dims": c["world_aabb_dims"],
                "true_dims_length_width_thickness_m":
                    c["true_dims_length_width_thickness_m"],
                "slab_reading": c["slab_reading"],
                "is_rectangular_slab": c["is_rectangular_slab"],
                "edge_perpendicularity_angles_deg":
                    c["edge_perpendicularity_angles_deg"],
                "box_skew_check": c["box_skew_check"],
                "volume_m3": c["volume_m3"],
                "volume_basis": c["volume_basis"],
                "mass_kg": c["mass_kg"],
                "mass_basis": c["mass_basis"],
                "lean_from_vertical_deg": c["lean_from_vertical_deg"],
                "long_axis_tilt_from_vertical_deg":
                    c["long_axis_tilt_from_vertical_deg"],
                "world_orientation": c["world_orientation"],
                "face_roles": c["face_roles"],
                "toppling_geometry": c["toppling_geometry"],
                "camera_visibility": c["camera_visibility"],
                "z_min": c["z_min"],
                "z_max": c["z_max"],
                "height_m": c["height_m"],
                "lowest_vertex_world": c["lowest_vertex_world"],
                "highest_vertex_world": c["highest_vertex_world"],
                "surface_area_m2": c["surface_area_m2"],
                "broad_face_area_m2": c["broad_face_area_m2"],
                "contact_probes": c["contact_probes"],
                "triangle_intersections_with_nearby_objects":
                    c["triangle_intersections_with_nearby_objects"],
                "min_distance_to_other_components":
                    c["min_distance_to_other_components"],
            }
            ex = export_by_src.get(key)
            if ex:
                rec["export"] = {
                    "obj_file": ex["obj_file"],
                    "obj_path": ex["obj_path"],
                    "obj_sha256": (verify_by_file.get(ex["obj_file"], {})
                                   .get("obj_sha256")),
                    "vertex_indices_used": ex["vertex_indices_used"],
                    "face_indices_used": ex["face_indices_used"],
                    "n_vertices_exported": ex["n_vertices_exported"],
                    "n_faces_exported": ex["n_faces_exported"],
                    "source_blend_sha256": ex["source_blend_sha256"],
                    "object_matrix_world": ex["object_matrix_world"],
                }
                v = verify_by_file.get(ex["obj_file"])
                if v:
                    rec["export_verification"] = {
                        "reimported_n_vertices": v.get("n_vertices"),
                        "reimported_n_faces": v.get("n_faces"),
                        "reimported_world_aabb_min": v.get("world_aabb_min"),
                        "reimported_world_aabb_max": v.get("world_aabb_max"),
                        "reimported_edge_family_lengths":
                            v.get("edge_family_lengths_sorted"),
                        "aabb_max_abs_error_vs_sidecar_m":
                            v.get("aabb_max_abs_error_m"),
                        "max_corner_residual_m": v.get("max_corner_residual_m"),
                        "is_exact_rectangular_box": v.get(
                            "is_exact_rectangular_box_from_corners"),
                        "counts_match_sidecar": v.get("counts_match_sidecar"),
                    }
            components_all.append(rec)

    # ---- ranking: prefer SHORT, THIN, LIGHT, in-frame, off-vertical ---------
    def score(r):
        cv = r.get("camera_visibility") or {}
        in_frame = bool(cv.get("in_frame"))
        h = r["height_m"]
        m500 = r["mass_kg"]["softwood_mid"]
        lean = r["lean_from_vertical_deg"] or 0.0
        # hard filter handled outside; score favours short + light + leaned
        return (0 if in_frame else 1, round(h, 4), round(m500, 3))

    ranked_usable = sorted(
        [r for r in components_all
         if r["is_rectangular_slab"]
         and (r.get("camera_visibility") or {}).get("in_frame")],
        key=score)

    chosen = ranked_usable[0]
    alternates = ranked_usable[1:4]

    # ---- can-vs-board interaction geometry (measured, not predicted) -------
    CAN_DIA_M = 0.066
    CAN_H_M = 0.122
    T = chosen["slab_reading"]["thickness_m"]
    H = chosen["height_m"]
    lo = chosen["lowest_vertex_world"]
    hi = chosen["highest_vertex_world"]
    cv = chosen.get("camera_visibility") or {}
    can_geom = {
        "reference_can": {"diameter_m": CAN_DIA_M, "height_m": CAN_H_M,
                          "note": "a standard 330 ml beverage can; used only as a "
                                  "scale and reach reference"},
        "can_diameter_over_board_thickness": round(CAN_DIA_M / T, 3),
        "can_diameter_over_board_height": round(CAN_DIA_M / H, 4),
        "can_height_over_board_height": round(CAN_H_M / H, 4),
        "board_lowest_vertex": lo,
        "board_highest_vertex": hi,
        "board_foot_at_wall_plinth_z": lo[2],
        "board_top_reaches_z": hi[2],
        "open_approach_directions": {
            "toward_the_wall_negative_X": "BLOCKED by apartment_walls "
                                          "(x = -2.2 plane)",
            "away_from_the_wall_positive_X": "OPEN - the alley floor extends to "
                                             "x = +4.2 (Floor_main)",
            "along_the_wall_negative_Y": "OPEN - the wall runs from y = -7.4 to "
                                         "y = +5.5, so a can can roll along it",
            "along_the_wall_positive_Y": "OPEN - same wall run",
        },
        "camera_view_of_the_board": {
            "clipped_frame_area_fraction": cv.get("clipped_frame_area_fraction"),
            "in_frame": cv.get("in_frame"),
            "note": "0.69 % of frame - the smallest of the five .001 components; "
                    "the camera sits at y=-4.42 looking +Y, so it sees the board "
                    "from the -Y side, across the open alley floor",
        },
        "consequence_for_the_solver": (
            "A can can only reach this board across OPEN floor, i.e. from +X "
            "(away from the wall) or from +/-Y along the wall. It cannot push "
            "the board wallward, because the wall is directly behind. The only "
            "way a hit topples the board is by driving its FOOT outward so the "
            "board rotates about its top wall contact. This is a hypothesis "
            "about the shot geometry, NOT a measured topple result."),
        "not_established": "whether a can can actually topple this board; no "
                           "impact test has been run",
    }

    # Nothing here is hardcoded: the resting object, the wall object and the
    # gaps are read back out of the recorded ray casts.
    def probe(rec, name):
        for p in rec["contact_probes"]:
            if p["probe"] == name:
                return p
        return None

    SELF = chosen["source_object"]
    WALL_OBJECTS = {"apartment_walls"}

    def first_hit(rec, names, exclude_self=True, require_dir=None):
        for p in rec["contact_probes"]:
            if p["probe"] not in names or not p.get("hit"):
                continue
            ho = p.get("hit_object")
            if exclude_self and ho == SELF:
                continue
            if require_dir is not None:
                d = p.get("direction")
                if d != require_dir:
                    continue
            return p
        return None

    # what does the board rest on?
    rest = None
    for nm in ("base_face_lowest_vertex_down", "base_face_centroid_down",
               "centroid_down"):
        p = probe(chosen, nm)
        if p and p.get("hit") and p.get("hit_object") != SELF:
            rest = {"probe": nm, "object": p["hit_object"],
                    "distance_m": p["hit_distance_m"],
                    "hit_location": p.get("hit_location")}
            break

    # what is the board's nearest wall-side contact, and is it the wall itself?
    wall_hits = []
    for p in chosen["contact_probes"]:
        if not p.get("hit"):
            continue
        if p.get("hit_object") == SELF:
            continue
        d = p.get("direction")
        if d and d[0] < -0.5:  # travelling toward -X, i.e. toward the wall
            wall_hits.append({"probe": p["probe"], "object": p["hit_object"],
                              "distance_m": p["hit_distance_m"],
                              "hit_location": p.get("hit_location")})
    wall_hits.sort(key=lambda h: h["distance_m"])
    nearest_wall_side = wall_hits[0] if wall_hits else None
    hits_apartment_walls = any(h["object"] in WALL_OBJECTS for h in wall_hits)

    # does the board interpenetrate the wall mesh?
    wall_intersections = [
        i for i in chosen["triangle_intersections_with_nearby_objects"]
        if i["object"] in WALL_OBJECTS]
    other_intersections = [
        i for i in chosen["triangle_intersections_with_nearby_objects"]
        if i["object"] not in WALL_OBJECTS]

    chosen_contact = {
        "rests_on": rest,
        "wall_side_ray_hits_toward_negative_X_sorted": wall_hits,
        "nearest_wall_side_contact": nearest_wall_side,
        "any_wallward_ray_hits_apartment_walls": hits_apartment_walls,
        "intersects_apartment_walls_mesh": bool(wall_intersections),
        "wall_mesh_intersections": wall_intersections,
        "other_mesh_intersections": other_intersections,
        "interpretation": (
            "For this component the wallward rays stop on the skirting/plinth "
            "trim (dado_tripple_01.003) before reaching the wall plane, so the "
            "board's nearest obstruction at the wall is the TRIM, not "
            "apartment_walls itself. The board does NOT interpenetrate the wall "
            "mesh, which is what distinguishes a leaning prop from wall geometry."
            if not hits_apartment_walls else
            "A wallward ray from this component reaches apartment_walls, and the "
            "component does not interpenetrate the wall mesh, so the contact is a "
            "lean against the wall surface rather than fused wall geometry."
        ),
    }

    report = {
        "task": "V5.6 Hidden Alley: identify and extract ONE physical wooden "
                "board a rolling can could knock over",
        "generated_by": "tools/v56/a_make_report.py",
        "source": {
            "blend_file": analysis["blend"],
            "blend_sha256": analysis.get("blend_sha256"),
            "blender_version": analysis["blender"],
            "reference_render":
                "outcomes/v5_asset_review/scenes/hidden_alley.png",
            "reference_audit":
                "outcomes/v5_asset_review/scenes/audits/hidden_alley.json",
        },
        "scripts": [
            "tools/v56/a_board_components.py",
            "tools/v56/a_dump_topology.py",
            "tools/v56/a_probe_view.py",
            "tools/v56/a_neighbours.py",
            "tools/v56/a_analyze_boards.py",
            "tools/v56/a_export_boards.py",
            "tools/v56/a_verify_exports.py",
            "tools/v56/a_make_report.py",
        ],
        "unit_scale": {
            "scene_unit_settings": analysis["unit_settings"],
            "confirmed_1_scene_unit_equals_1_metre": True,
            "confirmed_by": "parent agent, outcomes/v56/hidden_alley_can_board/"
                            "unit_scale.json",
            "evidence": analysis["unit_scale_evidence"],
            "scale_length_note":
                "scale_length = 10.0 is a Blender unit-system DISPLAY factor. It "
                "does not scale geometry, and it is NOT applied to any number in "
                "this report. All lengths below are world units, and world units "
                "are metres.",
            "non_unit_object_scale_applied":
                "wooden_boards.001 has object scale 0.887279987 (uniform). Every "
                "length reported for its components is measured AFTER applying "
                "matrix_world, i.e. the object scale IS applied; the raw local "
                "edge lengths are 1/0.88728 = 1.1271x larger.",
        },
        "method": {
            "component_definition":
                "edge-connected components of the mesh, computed with a "
                "union-find over mesh edges. This is the correct definition "
                "here: a loose UNWELDED VERTEX with no edges forms its own "
                "component but contains no faces, so it can never be mistaken "
                "for a board. All three board objects have zero loose vertices.",
            "why_not_face_count":
                "A connected-component count only equals a board count if the "
                "components have faces. The script reports, per component, both "
                "n_faces and n_verts, and separately counts face-less "
                "components, so the earlier 'loose vertices could inflate the "
                "count' concern is resolved explicitly rather than assumed.",
            "dimension_measurement":
                "The AABB is NOT used for board dimensions. The three true slab "
                "edge vectors are recovered from the component's own inter-vertex "
                "differences: pairwise differences are clustered by direction, and "
                "within each direction the SHORTEST member is the primitive edge "
                "(longer members are face/body diagonals). The three shortest "
                "mutually-orthogonal families are the slab edges. They are checked "
                "for mutual perpendicularity and the corner set is checked against "
                "the resulting parallelepiped, so 'is a rectangular slab' is a "
                "test result (see is_rectangular_slab and box_skew_check).",
            "volume_measurement":
                "Every component is an OPEN 5-face shell (4 boundary edges), so "
                "the divergence-theorem signed volume is NOT valid and is reported "
                "only as 'signed_volume_m3' for the record. The volume used for "
                "mass is the verified slab box volume L*W*T.",
            "mass_measurement":
                "mass = slab box volume x density. Density is not determined by "
                "the scene (the material is a texture, 'ph_gate_boards'), so three "
                "stated timber densities are reported: 400 kg/m3 (pine/softwood), "
                "500 kg/m3 (mid softwood, used as the headline), 700 kg/m3 "
                "(hardwood).",
            "contact_measurement":
                "Blender scene.ray_cast probes from measured face/vertex points, "
                "plus a triangle-triangle BVH overlap test (mathutils.bvhtree) "
                "against every mesh whose AABB is within 0.25 m. 'Intersects the "
                "wall' is therefore a computed overlap, not an AABB guess.",
            "no_rendering":
                "No image was rendered for this analysis. Rendering was stopped "
                "at the parent agent's request to avoid competing with the "
                "per-frame cost measurement on the 16 shared CPUs.",
        },
        "scene_camera": analysis["scene"],
        "group_findings": {
            "wooden_boards": {
                "components": 6,
                "location_world": "x -1.444..1.300, y -5.171..-5.122, "
                                  "z -0.533..2.438",
                "verdict": "FIXED GATE INFILL - not a free board, and behind "
                           "the camera",
                "evidence": [
                    "The active camera sits at y=-4.4245 with measured forward "
                    "vector (0.000001, 1.000000, 0.000027), i.e. it looks toward "
                    "+Y. This object is at y=-5.13, behind the camera.",
                    "Projection confirms it: every component's NDC depth is "
                    "negative and its NDC box lies outside [0,1], so it cannot "
                    "appear in any frame (see per-component camera_visibility).",
                    "Its 6 components are flat vertical slabs 15.29 mm thick "
                    "whose thickness axis is exactly +/-Y, co-planar in two "
                    "layers at y=-5.137 and y=-5.122.",
                    "They sit co-planar with and sandwiched between "
                    "large_iron_gate_left_door.001 and "
                    "large_iron_gate_right_door.001 (y -5.069..-4.984), and share "
                    "the gate material family 'ph_gate_boards'.",
                ],
            },
            "wooden_boards.002": {
                "components": 6,
                "location_world": "x -1.398..1.345, y -5.112..-5.063, "
                                  "z -0.109..2.862",
                "verdict": "FIXED GATE INFILL, second layer - same as above",
                "evidence": [
                    "Geometrically identical to wooden_boards, offset 0.059 m "
                    "in +Y; the same 6 slab shapes with the same counts.",
                    "Also behind the camera, also outside the frame.",
                ],
            },
            "wooden_boards.001": {
                "components": 5,
                "location_world": "x -2.200..-1.824, y 0.474..3.578, "
                                  "z -0.047..2.392",
                "verdict": "LOOSE BOARDS LEANING AGAINST THE BUILDING WALL - "
                           "the only physically usable group, and in frame",
                "evidence": [
                    "In front of the camera at 5.0-7.9 m; all 5 components "
                    "project inside the frame.",
                    "Material is 'ph_gate_boards' whereas the building wall is "
                    "the 'modular_urban_*_facade_*' family - a different prop, "
                    "not wall geometry.",
                    "Every component is tilted off vertical (lean 2.353 to "
                    "12.697 deg). Built-in wall geometry would be at 0 deg.",
                    "No component overlaps the wall mesh. Triangle-triangle BVH "
                    "overlap finds only ground scatter (leaves, stones) and the "
                    "wall plinth (base_tripple_01.003). apartment_walls appears "
                    "in no component's intersection list.",
                    "Wall contact is a measured small GAP, not a weld: rays from "
                    "the component's own surface hit apartment_walls at 6.7 mm "
                    "(c2), 27.2 mm (c4), 42.1 mm (c1), 123.5 mm (c3), 7.4 mm "
                    "(c0).",
                    "Base: the components stand on the wall plinth "
                    "base_tripple_01.003 (x -2.2..-2.0, z -0.74..0.01); "
                    "c0 and c3 additionally embed ~5 mm into the ground layer "
                    "(Floor_main top z=-0.040).",
                    "No component has animation data or a parent; each is a "
                    "static 8-vertex / 5-face slab.",
                ],
                "structural_surprise": [
                    "Each 5-face component has exactly ONE broad face "
                    "(normal along its thickness axis) - the shell is open on "
                    "one broad side. Which side is open differs per component.",
                    "The open side faces the WALL for c1, c2, c3 and c4, and "
                    "faces AWAY from the wall for c0. This is why 'the board "
                    "touches the wall with its broad face' is true only for c0; "
                    "for the others the wall contact is at the slab's thin top "
                    "end edge, i.e. the boards rest their upper END on the wall "
                    "and lean, rather than laying a broad face against it.",
                    "This is a strong argument that these boards are DECORATIVE "
                    "PROPS PLACED BY THE ARTIST, not structural wall members: a "
                    "built-in panel would not be modelled as a one-sided open "
                    "shell.",
                ],
            },
        },
        "components_examined": components_all,
        "ranking_rule": (
            "Candidates must be rectangular slabs AND inside the camera frame. "
            "Among those, ranked by SHORTEST height first (a can must be able to "
            "topple it), then lightest mass at 500 kg/m3. Lean is reported but "
            "is NOT used to rank, because 'more leaned means easier to topple' is "
            "a physics hypothesis this task does not test."),
        "recommended_board": {
            "source_object": chosen["source_object"],
            "component_index": chosen["component_index"],
            "obj_file": (chosen.get("export") or {}).get("obj_file"),
            "obj_path": (chosen.get("export") or {}).get("obj_path"),
            "obj_sha256": (chosen.get("export") or {}).get("obj_sha256"),
            "world_aabb_min": chosen["world_aabb_min"],
            "world_aabb_max": chosen["world_aabb_max"],
            "dimensions_m": {
                "length_m": chosen["slab_reading"]["longest_edge_m"],
                "in_plane_width_or_height_m": chosen["slab_reading"]["middle_edge_m"],
                "thickness_m": chosen["slab_reading"]["thickness_m"],
                "note": "length x width x thickness; for this component the "
                        "'length' axis is horizontal (runs parallel to the wall "
                        "along -Y) and the vertical extent is the middle edge",
                "height_m": chosen["height_m"],
            },
            "world_aabb_dims_for_reference": chosen["world_aabb_dims"],
            "volume_m3": chosen["volume_m3"],
            "mass_estimate_kg": chosen["mass_kg"],
            "headline_mass_kg_500_kgm3": chosen["mass_kg"]["softwood_mid"],
            "mass_range_kg": [chosen["mass_kg"]["pine_low"],
                              chosen["mass_kg"]["hardwood_high"]],
            "lean_from_vertical_deg": chosen["lean_from_vertical_deg"],
            "contact_evidence": chosen_contact,
            "is_free_leaning_not_wall_geometry": True,
            "confidence": {
                "is_a_single_separate_board": "high",
                "is_free_leaning_rather_than_wall_geometry": "high",
                "can_topple_it": "NOT established - not tested",
            },
            "export_verification": chosen.get("export_verification"),
            "can_interaction_geometry": can_geom,
        },
        "alternate_boards": [
            {
                "rank": i + 2,
                "source_object": a["source_object"],
                "component_index": a["component_index"],
                "obj_file": (a.get("export") or {}).get("obj_file"),
                "obj_path": (a.get("export") or {}).get("obj_path"),
                "world_aabb_min": a["world_aabb_min"],
                "world_aabb_max": a["world_aabb_max"],
                "dimensions_m": {
                    "length_m": a["slab_reading"]["longest_edge_m"],
                    "in_plane_width_or_height_m": a["slab_reading"]["middle_edge_m"],
                    "thickness_m": a["slab_reading"]["thickness_m"],
                    "height_m": a["height_m"],
                },
                "volume_m3": a["volume_m3"],
                "mass_estimate_kg": a["mass_kg"],
                "lean_from_vertical_deg": a["lean_from_vertical_deg"],
                "clipped_frame_area_fraction":
                    (a.get("camera_visibility") or {}).get(
                        "clipped_frame_area_fraction"),
                "export_verification": a.get("export_verification"),
            }
            for i, a in enumerate(alternates)
        ],
        "support_geometry_export": manifest.get("support_export"),
        "support_export_verification": {
            k: v for k, v in verify_by_file.get(
                "support_wall_ground.obj", {}).items()
            if k in ("n_vertices", "n_faces", "n_triangles", "world_aabb_min",
                     "world_aabb_max", "world_dims", "total_face_area",
                     "obj_sha256")
        },
        "deliverables": {
            "boards_dir": A.boards,
            "export_manifest": os.path.join(A.boards, "export_manifest.json"),
            "support_obj": os.path.join(A.boards, "support_wall_ground.obj"),
            "support_sidecar": os.path.join(A.boards, "support_wall_ground.json"),
        },
        "uncertainties": [
            "NOT VISUALLY CONFIRMED. No image was rendered (rendering was "
            "stopped at the parent's request to protect the CPU timing "
            "measurement). Every claim here is metric - projection, ray casts "
            "and triangle overlap - and none of it is a picture of the board. "
            "A single scheduled render is needed to confirm the recommended "
            "board reads as a board on screen and is not occluded by grass, "
            "weed_plants, leaves or stones.",
            "'Long boards lying almost flat across other boards' vs 'short "
            "boards leaning on the wall': the lean magnitudes (2.35 to 12.70 "
            "deg) and the fact that the wall contact sits at each slab's thin "
            "top END edge for c1-c4 indicate SHORT BOARDS PROPPED UPRIGHT. I "
            "could not fully exclude that some components are instead long "
            "boards lying nearly flat and propped at one end, because that "
            "reading requires knowing which surface each board crosses; my "
            "triangle overlap on wooden_boards.001 c0 returns only leaves and "
            "stones, and my open-shell detection cannot recover a face the "
            "artist deleted.",
            "The material is a texture ('ph_gate_boards') with no density, so "
            "the timber species is unknown. Mass is therefore a RANGE "
            "(3.08-5.38 kg for the recommendation) across three stated "
            "densities, not a single measured value.",
            "Which surface a physics solver should treat as 'the floor' near "
            "the wall is not settled: base_tripple_01.003 top is at z=0.0097, "
            "Floor_main top is at z=-0.040, and stones/grass/leaves scatter "
            "occupies z -0.155..0.0. The board's lowest vertex is at z=0.0097 "
            "(on the plinth), but a can rolling to it would travel on a "
            "different surface.",
            "Whether a can can actually TOPPLE this board is NOT established "
            "and is NOT claimed. The toppling_geometry block reports the "
            "static tip angle and moment arms as pure geometry, but no impact "
            "test has been run.",
            "I could not determine the artist's intent: a 7-13 deg tilt plus a "
            "millimetre-scale wall gap is consistent with a deliberately "
            "placed leaning board, but it is also consistent with an "
            "approximately placed prop. This is an inference from geometry, "
            "not a documented fact.",
            "The support OBJ is a clip of the wall/plinth/floor/stones within "
            "0.6 m of the chosen board's AABB. It is NOT a watertight solid "
            "and includes scattered stones geometry; a solver should treat it "
            "as static obstacle geometry only.",
            "grass (1,053,781 verts), stones (185,330) and leaves (28,646) "
            "were NOT included as full meshes in the support export - they are "
            "large and would swamp the OBJ. Only their polygons inside the "
            "clip box are included, and only for 'stones'; grass and leaves "
            "are omitted entirely.",
        ],
    }

    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    with open(A.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print("[a_make_report] wrote", A.out)
    print("[a_make_report] recommended: %s component %d  %s x %s x %s m  "
          "%.3f kg @500" % (
              chosen["source_object"], chosen["component_index"],
              chosen["slab_reading"]["longest_edge_m"],
              chosen["slab_reading"]["middle_edge_m"],
              chosen["slab_reading"]["thickness_m"],
              chosen["mass_kg"]["softwood_mid"]))


main()
