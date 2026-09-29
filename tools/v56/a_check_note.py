"""a_check_note.py -- V5.6 fact-check A_board_extraction.md against board_selection.json.

Control-python only. Re-derives each quantitative claim made in the markdown
note from the JSON report and prints PASS/FAIL, so the note cannot overstate a
number that the machine-readable report contradicts.

Run:
  python a_check_note.py --json <board_selection.json> --work <work dir>
"""

import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--work", required=True)
    A = ap.parse_args()
    d = json.load(open(A.json, encoding="utf-8"))
    a = json.load(open(os.path.join(A.work, "analysis.json"), encoding="utf-8"))
    v = json.load(open(os.path.join(A.work, "verification.json"), encoding="utf-8"))

    checks = []

    def ck(label, got, want, tol=0.0):
        ok = (abs(got - want) <= tol) if isinstance(want, (int, float)) else (got == want)
        checks.append((label, got, want, ok))

    rb = d["recommended_board"]
    dims = rb["dimensions_m"]
    ck("rec length 1.461221", dims["length_m"], 1.461221, 1e-6)
    ck("rec in-plane 0.387728", dims["in_plane_width_or_height_m"], 0.387728, 1e-6)
    ck("rec thickness 0.013568", dims["thickness_m"], 0.013568, 1e-6)
    ck("rec height 0.389565", dims["height_m"], 0.389565, 1e-6)
    ck("rec mass@500 3.84356", rb["mass_estimate_kg"]["softwood_mid"], 3.84356, 1e-5)
    ck("rec mass low 3.07485", rb["mass_estimate_kg"]["pine_low"], 3.07485, 1e-5)
    ck("rec mass high 5.38099", rb["mass_estimate_kg"]["hardwood_high"], 5.38099, 1e-5)
    ck("rec lean 12.6969", rb["lean_from_vertical_deg"], 12.6969, 1e-4)
    ck("rec volume 0.007687", rb["volume_m3"], 0.007687, 1e-6)
    ck("rec aabb min x", rb["world_aabb_min"][0], -2.152816, 1e-6)
    ck("rec aabb max z", rb["world_aabb_max"][2], 0.399251, 1e-6)

    # component counts
    byobj = {}
    for c in d["components_examined"]:
        byobj.setdefault(c["source_object"], []).append(c)
    ck("wooden_boards comps", len(byobj["wooden_boards"]), 6)
    ck("wooden_boards.001 comps", len(byobj["wooden_boards.001"]), 5)
    ck("wooden_boards.002 comps", len(byobj["wooden_boards.002"]), 6)
    ck("total components examined", len(d["components_examined"]), 17)

    # every component 8/5 with no loose verts and all rectangular + open
    bad = [c for c in d["components_examined"]
           if not (c["n_verts"] == 8 and c["n_faces"] == 5)]
    ck("all components are 8v/5f", len(bad), 0)
    notslab = [c for c in d["components_examined"] if not c["is_rectangular_slab"]]
    ck("all components rectangular slabs", len(notslab), 0)
    closed = [c for c in d["components_examined"] if c["is_closed_solid"]]
    ck("no component is a closed solid", len(closed), 0)
    openedges = {c["boundary_edge_count"] for c in d["components_examined"]}
    ck("all have 4 boundary edges", list(openedges), [4])

    # loose vertices across all three objects
    loose = sum(o["mesh"]["n_loose_verts_total"] for o in [])
    # read from components.json if present
    cp = os.path.join(A.work, "components.json")
    if os.path.exists(cp):
        cc = json.load(open(cp, encoding="utf-8"))
        tot = sum(o["mesh"]["n_loose_verts_total"] for o in cc["objects"])
        ck("total loose verts in wooden_boards*", tot, 0)
        faceonly = sum(o["mesh"]["n_components_loose_verts_only"] for o in cc["objects"])
        ck("face-less components", faceonly, 0)
    cw = os.path.join(A.work, "components_weld1mm.json")
    if os.path.exists(cw):
        w = json.load(open(cw, encoding="utf-8"))
        got = [o["mesh"]["n_components_edge_connected"] for o in w["objects"]]
        ck("1mm-weld component counts unchanged", got, [6, 5, 6])

    # camera direction and behind-camera claim.
    # a_analyze_boards.py stores scene as a bare name; the camera details live
    # in components.json, so read them there.
    cp = os.path.join(A.work, "components.json")
    cc = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else None
    if cc:
        cam = cc["scene"]["camera"]
        ck("camera at y=-4.424526", cam["location"][1], -4.424526, 1e-6)
        ck("camera clip_start 0.1", cam["clip_start"], 0.1, 1e-6)
        ck("camera clip_end 1000", cam["clip_end"], 1000.0, 1e-6)
        ck("unit system METRIC", cc["scene"]["unit_system"], "METRIC")
        ck("scale_length 10", cc["scene"]["scale_length"], 10.0)
        ck("blend sha", cc["blend_sha256"],
           "be1247889cee3ce10028ee1ef1066a96728b3c2aa191ad12b51cc3b578fa4ae9")
    behind = all(not (c["camera_visibility"] or {}).get("in_front_of_camera")
                 for c in byobj["wooden_boards"] + byobj["wooden_boards.002"])
    ck("gate boards all behind camera", behind, True)
    inframe = all((c["camera_visibility"] or {}).get("in_frame")
                  for c in byobj["wooden_boards.001"])
    ck("all .001 components in frame", inframe, True)

    # wall interpenetration
    for c in d["components_examined"]:
        hit = [i["object"] for i in c["triangle_intersections_with_nearby_objects"]]
        ck("c %s/%d does not intersect apartment_walls" % (c["source_object"], c["component_index"]),
           "apartment_walls" in hit, False)

    # alternates table
    alt = d["alternate_boards"]
    ck("3 alternates", len(alt), 3)
    ck("alt1 mass 7.33513", alt[0]["mass_estimate_kg"]["softwood_mid"], 7.33513, 1e-4)
    ck("alt2 mass 7.53885", alt[1]["mass_estimate_kg"]["softwood_mid"], 7.53885, 1e-4)
    ck("alt3 mass 6.78043", alt[2]["mass_estimate_kg"]["softwood_mid"], 6.78043, 1e-4)

    # thickness identical across .001
    th = {c["true_dims_length_width_thickness_m"][2] for c in byobj["wooden_boards.001"]}
    ck("all .001 same thickness", len(th), 1)
    ck("that thickness ~0.013568", list(th)[0], 0.013568, 1e-6)
    # object scale
    sc = byobj["wooden_boards.001"][0]["source_object_scale"]
    ck("object scale 0.88728", sc[0], 0.88728, 1e-6)
    ck("local thickness = world / scale", 0.013568 / sc[0], 0.015292, 1e-5)

    # verification block
    ver = rb["export_verification"]
    ck("verify nv", ver["reimported_n_vertices"], 8)
    ck("verify nf", ver["reimported_n_faces"], 5)
    ck("verify aabb err 0", ver["aabb_max_abs_error_vs_sidecar_m"], 0.0)
    ck("verify corner residual", ver["max_corner_residual_m"], 5.71472e-07, 1e-12)
    ck("verify exact box", ver["is_exact_rectangular_box"], True)
    ck("verify edge lens match",
       ver["reimported_edge_family_lengths"][:3], [0.013568, 0.387728, 1.461221])

    # support
    sup = d["support_export_verification"]
    ck("support verts 3007", sup["n_vertices"], 3007)
    ck("support faces 5267", sup["n_faces"], 5267)
    ck("support tris 5592", sup["n_triangles"], 5592)
    ck("support aabb min", sup["world_aabb_min"], [-2.2, 0.5, -0.74])
    ck("support aabb max", sup["world_aabb_max"], [-1.36698, 3.601909, 1.0])

    # blending/units
    ck("unit scale flagged", d["unit_scale"]["confirmed_1_scene_unit_equals_1_metre"], True)
    ck("scale_length 10 not applied", d["unit_scale"]["scene_unit_settings"]["scale_length"], 10.0)
    ck("num verification obj files", len(v["objects"]), 5)

    fails = [c for c in checks if not c[3]]
    for label, got, want, ok in checks:
        print("%s  %-58s got=%s want=%s" % ("PASS" if ok else "FAIL", label,
                                            _s(got), _s(want)))
    print()
    print("%d checks, %d FAIL" % (len(checks), len(fails)))
    return 1 if fails else 0


def _s(x):
    if isinstance(x, float):
        return "%.8g" % x
    return str(x)[:70]


raise SystemExit(main())
