"""V5.5 stage 03 section 6: source-vs-runtime comparison and fixed-seed alignment images.

03 section 6 requires two things that a layer report cannot express on its own:

  1. a SOURCE-COPY DIFFERENCE LIST -- an explicit, complete account of every way the runtime
     copy differs from the authored source, so nothing about the scene changes silently;
  2. FIXED-SEED ALIGNMENT IMAGES -- the source scene rendered as-is FIRST, then the runtime
     copy's initial state, from the same camera and seed, so a regression in lighting,
     materials or object placement is visible rather than asserted.

Both are produced here from the same camera, resolution and sampling settings, so the two images
are directly comparable. The comparison is intentionally GEOMETRIC and MATERIAL rather than
visual-only, because the reviewer of this record cannot see images: for every object the source
and runtime states are compared numerically, and the render pair is delivered as the artefact
that a human can open.

Deliverables:
  source_runtime_diff.json      per-object difference list with reasons
  alignment/source_*.png        source as-is
  alignment/runtime_*.png       runtime initial state
  alignment/compare.json        numeric comparison of the two initial states
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SCENE_NAME = ARGS[0] if ARGS else "italian_flat"
ROOT = Path(r"D:\workspace\project1_database")

SRC = ROOT / "models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend"
RUNTIME = (ROOT / "outcomes/v55/scenes/italian_flat/runtime/italian_flat_runtime.blend")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
OUT = SCENES / "alignment"

LAYERS = ["environment_static_visual", "environment_static_collision",
          "interaction_dynamic_visual", "interaction_dynamic_collision",
          "authored_lighting", "source_archive"]

# The archive layer is deliberately hidden in the runtime view, so the comparison records the
# layers a viewer would actually see plus the archived count, rather than treating the hidden
# archive as a difference in content.
VISIBLE_LAYERS = ["environment_static_visual", "environment_static_collision",
                  "interaction_dynamic_visual", "interaction_dynamic_collision",
                  "authored_lighting"]


def scene_facts(label: str) -> dict:
    """Numeric description of the current scene: objects, transforms, materials, lights, world.

    IMPORTANT -- the geometry of every mesh is read with `hide_viewport` temporarily CLEARED.
    Blender's evaluated depsgraph skips disabled objects, so a hidden object evaluates to its
    BASE mesh with no modifiers applied. The layer build hides the 464 archived source
    instances, and reading them as-is made 126 objects look as though they had lost geometry
    (`Balcony` appeared to go 300 -> 20 triangles) and 76 look as though they had shrunk.
    Forcing evaluation on both sides proved the geometry is in fact identical -- 0 mismatches
    across all 126 -- so the comparison must force it too, or it reports a fidelity failure that
    is an artefact of how it measured. Hiding is restored before returning.
    """
    hidden_saved: dict = {}
    for obj in bpy.data.objects:
        if obj.hide_viewport:
            hidden_saved[obj.name] = True
            obj.hide_viewport = False
    if hidden_saved:
        bpy.context.view_layer.update()

    deps = bpy.context.evaluated_depsgraph_get()
    facts: dict = {"label": label, "objects": {}, "lights": {}, "materials": {},
                   "world": {}, "collections": [], "counts": {},
                   "force_evaluated_hidden": len(hidden_saved)}
    for c in bpy.data.collections:
        facts["collections"].append(c.name)
    try:
        for obj in bpy.data.objects:
            ev = obj.evaluated_get(deps)
            try:
                me = ev.to_mesh()
            except Exception:
                me = None
            tris = 0
            dims = None
            if me is not None:
                me.calc_loop_triangles()
                tris = len(me.loop_triangles)
                if len(me.vertices):
                    xs = [v.co for v in me.vertices]
                    mn = [min(v[i] for v in xs) for i in range(3)]
                    mx = [max(v[i] for v in xs) for i in range(3)]
                    dims = [round(mx[i] - mn[i], 6) for i in range(3)]
                ev.to_mesh_clear()
            facts["objects"][obj.name] = {
                "type": obj.type,
                "location": [round(v, 6) for v in obj.location],
                "dimensions": [round(v, 6) for v in obj.dimensions] if obj.type == "MESH" else None,
                "evaluated_dimensions": dims,
                "evaluated_triangles": tris,
                # Visibility is recorded from the SAVED state, not the forced state, so the
                # layer build's hiding is still reported as a difference.
                "hide_viewport": bool(hidden_saved.get(obj.name, obj.hide_viewport)),
                "hide_render": bool(obj.hide_render),
                "collections": sorted(c.name for c in obj.users_collection),
                "materials": sorted(m.name for m in obj.data.materials
                                    if m is not None) if obj.type == "MESH" else [],
                "modifiers": [m.type for m in getattr(obj, "modifiers", [])],
            }
            if obj.type == "LIGHT":
                facts["lights"][obj.name] = {
                    "type": obj.data.type,
                    "energy": round(float(obj.data.energy), 6),
                    "color": [round(float(c), 6) for c in obj.data.color],
                    "location": [round(v, 6) for v in obj.location],
                }
    finally:
        for name in hidden_saved:
            o = bpy.data.objects.get(name)
            if o is not None:
                o.hide_viewport = True
        if hidden_saved:
            bpy.context.view_layer.update()
    for m in bpy.data.materials:
        nodes = []
        if m.use_nodes and m.node_tree:
            for n in m.node_tree.nodes:
                nodes.append(n.type)
        facts["materials"][m.name] = {"use_nodes": bool(m.use_nodes),
                                      "node_types": sorted(set(nodes)),
                                      "blend_method": getattr(m, "blend_method", None)}
    w = bpy.context.scene.world
    if w is not None:
        facts["world"] = {"name": w.name, "use_nodes": bool(w.use_nodes)}
    facts["counts"] = {
        "objects": len(bpy.data.objects),
        "meshes": len([o for o in bpy.data.objects if o.type == "MESH"]),
        "lights": len([o for o in bpy.data.objects if o.type == "LIGHT"]),
        "materials": len(bpy.data.materials),
        "cameras": len([o for o in bpy.data.objects if o.type == "CAMERA"]),
    }
    return facts


def layer_visibility(facts: dict) -> dict:
    """Which layers hold which objects, and how many are visible."""
    per: dict = {name: [] for name in LAYERS}
    for name, o in facts["objects"].items():
        for c in o["collections"]:
            if c in per:
                per[c].append(name)
    visible = sum(1 for o in facts["objects"].values()
                  if not o["hide_viewport"] and not o["hide_render"])
    return {"per_layer": {k: sorted(v) for k, v in per.items()},
            "layer_counts": {k: len(v) for k, v in per.items()},
            "visible_objects": visible,
            "hidden_objects": len(facts["objects"]) - visible}


def setup_camera() -> dict:
    """One camera for both renders.

    The framing is a plain three-quarter view of the interaction region, chosen so the table,
    the tray and the props are all inside the frame. It is identical for the source and the
    runtime render, which is what makes the pair an alignment check: any difference between the
    images comes from the scene, not from the camera.
    """
    cam = bpy.data.objects.get("V55 Align Camera")
    if cam is None:
        cam_data = bpy.data.cameras.new("V55 Align Camera")
        cam = bpy.data.objects.new("V55 Align Camera", cam_data)
        bpy.context.scene.collection.objects.link(cam)
    cam.data.lens = 50.0
    target = (1.52, 7.42, 0.62)
    cam.location = (1.52, 6.35, 1.42)
    # Aim at the interaction region. Blender cameras look down their local -Z with +Y up, so the
    # rotation is built from the direction vector rather than guessed as an Euler triple.
    import mathutils
    direction = mathutils.Vector(target) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return {"name": cam.name, "location": list(cam.location), "lens_mm": cam.data.lens,
            "target": list(target),
            "rotation_euler": [round(v, 6) for v in cam.rotation_euler],
            "distance_m": round(direction.length, 6)}


def render_to(path: Path, samples: int = 32, res=(1280, 720)) -> dict:
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.seed = 0
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    sc.frame_set(1)
    bpy.ops.render.render(write_still=True)
    ok = path.is_file()
    print(f"  rendered {path.name}: exists={ok} "
          f"bytes={path.stat().st_size if ok else 0}")
    return {"path": str(path), "exists": bool(ok),
            "bytes": path.stat().st_size if ok else 0,
            "samples": samples, "resolution": list(res), "seed": 0, "frame": 1}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"scene": SCENE_NAME, "source": str(SRC), "runtime": str(RUNTIME)}
    print("=" * 78)
    print(f"=== stage 03 section 6: source vs runtime, scene {SCENE_NAME} ===")

    if not SRC.is_file():
        raise SystemExit(f"FATAL: source blend missing: {SRC}")
    if not RUNTIME.is_file():
        raise SystemExit(f"FATAL: runtime blend missing: {RUNTIME}")

    # ---- pass 1: the SOURCE exactly as authored ---------------------------------------
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    src_facts = scene_facts("source")
    print(f"  source: {src_facts['counts']}")
    cam_info = setup_camera()
    report["camera"] = cam_info
    report["source_render"] = render_to(OUT / "source_as_authored.png")

    # ---- pass 2: the RUNTIME copy ------------------------------------------------------
    bpy.ops.wm.open_mainfile(filepath=str(RUNTIME))
    rt_facts = scene_facts("runtime")
    print(f"  runtime: {rt_facts['counts']}")
    # The align camera must be created AGAIN here. It was added to the SOURCE session only and
    # was never saved into either .blend, so after this second open_mainfile the active camera
    # is the runtime scene's own (`Cam Pouf Details`). Reusing the source camera without
    # recreating it rendered the runtime from a completely different viewpoint -- mean |diff|
    # 154.8/255 across the whole frame -- which is a measurement of two different cameras, not
    # of two scenes. `setup_camera` is idempotent by name, so calling it per pass is safe.
    cam_info_runtime = setup_camera()
    report["camera_runtime"] = cam_info_runtime
    report["camera_identical"] = bool(
        cam_info_runtime["location"] == cam_info["location"]
        and cam_info_runtime["lens_mm"] == cam_info["lens_mm"]
        and cam_info_runtime["target"] == cam_info["target"]
    )
    print(f"  camera recreated for runtime; identical to source camera: "
          f"{report['camera_identical']}")
    src_layers = layer_visibility(src_facts)
    rt_layers = layer_visibility(rt_facts)
    report["runtime_render"] = render_to(OUT / "runtime_initial_state.png")

    # ---- difference list ---------------------------------------------------------------
    print("\n=== difference list ===")
    diffs: list[dict] = []

    def add(kind: str, obj: str, detail: str, reason: str) -> None:
        diffs.append({"kind": kind, "object": obj, "detail": detail, "reason": reason})

    src_objs, rt_objs = src_facts["objects"], rt_facts["objects"]
    for name in sorted(set(src_objs) - set(rt_objs)):
        add("object_absent_in_runtime", name, "present in source only",
            "unexpected: the runtime copy must not drop objects")
    for name in sorted(set(rt_objs) - set(src_objs)):
        add("object_added_in_runtime", name, "present in runtime only",
            "expected: the align camera and any layer-build helper")
    for name in sorted(set(src_objs) & set(rt_objs)):
        a, b = src_objs[name], rt_objs[name]
        if a["collections"] != b["collections"]:
            add("collection_changed", name,
                f"{a['collections']} -> {b['collections']}",
                "expected: stage 03 layer assignment")
        if a["hide_render"] != b["hide_render"] or a["hide_viewport"] != b["hide_viewport"]:
            add("visibility_changed", name,
                f"hide_viewport {a['hide_viewport']}->{b['hide_viewport']}, "
                f"hide_render {a['hide_render']}->{b['hide_render']}",
                "expected for archived source instances: hidden, never deleted")
        if a["evaluated_triangles"] != b["evaluated_triangles"]:
            add("triangle_count_changed", name,
                f"{a['evaluated_triangles']} -> {b['evaluated_triangles']}",
                "unexpected: geometry must not be modified by the layer build")
        if a["evaluated_dimensions"] and b["evaluated_dimensions"]:
            worst = max(abs(x - y) for x, y in
                        zip(a["evaluated_dimensions"], b["evaluated_dimensions"]))
            if worst > 1e-6:
                add("dimensions_changed", name,
                    f"{a['evaluated_dimensions']} -> {b['evaluated_dimensions']} "
                    f"(max delta {worst:.9f} m)",
                    "unexpected: the visual must be unmodified")
    for name in sorted(set(src_facts["lights"]) | set(rt_facts["lights"])):
        a = src_facts["lights"].get(name)
        b = rt_facts["lights"].get(name)
        if a is None or b is None:
            add("light_added_or_removed", name, f"source={a is not None} runtime={b is not None}",
                "unexpected: authored lighting must be preserved")
        elif a != b:
            add("light_changed", name, f"{a} -> {b}",
                "unexpected: 03 requires authored lighting preserved")
    for name in sorted(set(src_facts["materials"]) | set(rt_facts["materials"])):
        a = src_facts["materials"].get(name)
        b = rt_facts["materials"].get(name)
        if a is None or b is None:
            add("material_added_or_removed", name,
                f"source={a is not None} runtime={b is not None}",
                "unexpected: materials must be preserved, not simplified")
        elif a != b:
            add("material_changed", name, f"{a} -> {b}",
                "unexpected: 03 forbids bulk material simplification")
    if src_facts["world"] != rt_facts["world"]:
        add("world_changed", "scene.world", f"{src_facts['world']} -> {rt_facts['world']}",
            "unexpected: the authored World must be preserved")

    expected_kinds = {"collection_changed", "visibility_changed", "object_added_in_runtime"}
    unexpected = [d for d in diffs if d["kind"] not in expected_kinds]
    print(f"  total differences      : {len(diffs)}")
    print(f"    expected (layering)  : {len(diffs) - len(unexpected)}")
    print(f"    UNEXPECTED           : {len(unexpected)}")
    by_kind: dict = {}
    for d in diffs:
        by_kind[d["kind"]] = by_kind.get(d["kind"], 0) + 1
    for k in sorted(by_kind):
        print(f"      {k:32s} {by_kind[k]}")
    for d in unexpected[:15]:
        print(f"    UNEXPECTED {d['kind']}: {d['object']} -- {d['detail']}")

    report["differences"] = diffs
    report["difference_counts"] = by_kind
    report["unexpected_differences"] = unexpected
    report["source_layers"] = src_layers
    report["runtime_layers"] = rt_layers
    report["expected_difference_kinds"] = sorted(expected_kinds)

    # ---- support relations ------------------------------------------------------------
    layer_report_path = SCENES / "layer_report.json"
    if layer_report_path.is_file():
        lr = json.loads(layer_report_path.read_text(encoding="utf-8"))
        report["static_collision_objects"] = sorted(lr.get("static_collision", {}))
        report["dynamic_props"] = sorted(lr.get("dynamic_props", {}))
        report["soft_background"] = lr.get("soft_background", [])
        report["source_archive_count"] = len(lr.get("archived_static_originals", []))
        print(f"\n=== support relations ===")
        print(f"  static collision objects : {report['static_collision_objects']}")
        print(f"  dynamic props            : {report['dynamic_props']}")
        print(f"  soft background-only     : "
              f"{[s['name'] for s in report['soft_background']]}")
        print(f"  archived (hidden, kept)  : {report['source_archive_count']}")

    # The measured support chain, carried in from the raycast and proxy stages.
    ray_path = SCENES / "italian_flat_support_raycast.json"
    proxy_path = SCENES / "proxy_acceptance_final.json"
    if ray_path.is_file():
        report["support_raycast"] = json.loads(ray_path.read_text(encoding="utf-8"))
    if proxy_path.is_file():
        pa = json.loads(proxy_path.read_text(encoding="utf-8"))
        report["proxy_acceptance"] = {
            "floor_z": pa.get("floor_z"),
            "tray_bias_m": pa.get("tray", {}).get("bias_vs_floor_m"),
            "chosen": {k: v.get("chosen") for k, v in pa.get("props", {}).items()},
            "all_pass": pa.get("all_pass"),
        }
        print(f"  proxy acceptance         : all_pass={report['proxy_acceptance']['all_pass']} "
              f"chosen={report['proxy_acceptance']['chosen']}")

    p = OUT / "compare.json"
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")

    # ---- quantitative image comparison ------------------------------------------------
    # The two renders are the artefact a human reviewer opens, but "looks the same" is not a
    # measurement. Pillow is available in this Blender's Python, so the pair is compared
    # numerically as well: the framing is identical, so the far edges of the frame -- background
    # that neither stage touches -- must match tightly, and any real difference must be confined
    # to the interaction region where the layer build moves the props out of the archived static
    # instances.
    try:
        from PIL import Image
        import numpy as np

        ia = Image.open(OUT / "source_as_authored.png").convert("RGB")
        ib = Image.open(OUT / "runtime_initial_state.png").convert("RGB")
        img: dict = {"source_size": list(ia.size), "runtime_size": list(ib.size)}
        if ia.size == ib.size:
            na = np.asarray(ia, dtype=np.float32)
            nb = np.asarray(ib, dtype=np.float32)
            diff = np.abs(na - nb).max(axis=2)
            img["mean_abs_diff_0_255"] = round(float(diff.mean()), 6)
            img["max_abs_diff_0_255"] = round(float(diff.max()), 6)
            img["pixels_over_8"] = int((diff > 8).sum())
            img["pixels_over_8_fraction"] = round(float((diff > 8).mean()), 9)
            border = np.concatenate([
                diff[:8, :].ravel(), diff[-8:, :].ravel(),
                diff[:, :8].ravel(), diff[:, -8:].ravel(),
            ])
            img["border_mean_abs_diff"] = round(float(border.mean()), 6)
            img["border_max_abs_diff"] = round(float(border.max()), 6)
            img["framing_aligned"] = bool(border.mean() < 2.0)
            print("\n=== alignment image comparison ===")
            print(f"  mean |diff| {img['mean_abs_diff_0_255']:.4f}/255, "
                  f"max {img['max_abs_diff_0_255']:.1f}, "
                  f"pixels >8: {img['pixels_over_8']} "
                  f"({img['pixels_over_8_fraction']*100:.4f}%)")
            print(f"  frame border mean |diff| {img['border_mean_abs_diff']:.4f} "
                  f"-> framing aligned: {img['framing_aligned']}")
        report["alignment_image_comparison"] = img
    except Exception as exc:
        report["alignment_image_comparison"] = {
            "error": f"{type(exc).__name__}: {exc}",
            "note": "images were still produced; the numeric comparison did not run",
        }
        print(f"\n  image comparison unavailable: {type(exc).__name__}: {exc}")
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    ok = len(unexpected) == 0
    print(f"\nSOURCE/RUNTIME FIDELITY: {'PASS' if ok else 'FAIL'} "
          f"({len(unexpected)} unexpected differences)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
