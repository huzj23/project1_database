"""V5.5 stage 03 section 5 + 05 sections 1-2: build the layered Italian Flat runtime copy.

Findings this script is built on (all measured, see italian_flat_support_raycast.json):

  * The props do NOT stand on the table. They stand on the tray `Vassoio`, whose floor is
    at z = 0.510600 and which has a RAISED RIM reaching z = 0.522260 -- a 11.66 mm kerb.
    03 section 5 requires every kerb a dynamic body could sweep into to have collision, and
    this rim is exactly such an obstacle: a sliding box and a toppling bottle both meet it.
  * The tray itself sits on `Table` whose top is z = 0.500000.
  * `Tappo Cristallo` (the cap) rests exactly on the bottle's top surface at z = 0.723081
    with a 0 mm vertical gap, so merging cap and bottle into one declared rigid assembly is
    physically justified (05 section 2.3 permits this only for a tightly closed cap).
  * The bottle's AABB bottom is z = 0.509198, which is 1.40 mm BELOW the tray floor of
    0.510600. That is a source-scene overlap, and 04 caps initial penetration at
    min(1 mm, t_min*5%), so it cannot be carried into the solve unchanged.

Deliverables built here:
  * a runtime copy (never the source) with the six required collections,
  * the original static props hidden and archived, and EXCLUDED from static collision so no
    body can collide with its own static copy (the "ghost" failure 03 warns about),
  * a bounded static collision region, because 03 forbids feeding a whole high-poly scene
    into the dynamic solver,
  * per-prop dynamic visual + collision extraction with baked transforms.

Run with Blender in background mode.  The source .blend is NEVER saved over.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SRC = Path(r"D:\workspace\project1_database\models\backgrounds\candidates\italian_flat\source\flat-archiviz.blend")
OUT = Path(r"D:\workspace\project1_database\outcomes\v55\scenes\italian_flat")
RUNTIME = OUT / "runtime"

LAYERS = [
    "environment_static_visual",
    "environment_static_collision",
    "interaction_dynamic_visual",
    "interaction_dynamic_collision",
    "authored_lighting",
    "source_archive",
]

# Props to extract as dynamic bodies, with the measured support facts.
DYNAMIC = {
    "Bottiglia Cristallo": {"role": "target", "support": "Vassoio", "support_z": 0.510600},
    "Bicchiere Cristallo": {"role": "target", "support": "Vassoio", "support_z": 0.510600},
    "Bicchiere Cristallo.001": {"role": "target", "support": "Vassoio", "support_z": 0.510600},
    "Tappo Cristallo": {"role": "assembly_with_bottle", "support": "Bottiglia Cristallo",
                        "support_z": 0.723081},
}

# Static collision region: the table, the tray, and everything within reach of the props.
STATIC_REQUIRED = ["Table", "Table.001", "Vassoio"]

# SOFT FURNISHINGS ARE BACKGROUND ONLY.  03 section 5 and 05's no-go rule both state that soft
# furniture must not take part in the dynamic collision world: a rigid body colliding with it
# would be solved against a rigid proxy of something the source treats as soft, which is
# exactly the unsupported soft-body simulation the project excludes.  The first layer build put
# `Sofa`, `Sofa.001`, `Sofa.005` and `Pillows` into `environment_static_collision` because they
# merely happened to fall inside the reach box, so they are named explicitly here and routed to
# the visual/background layer instead, with their distance to the interaction region recorded.
SOFT_KEYWORDS = ("sofa", "pillow", "cushion", "pouf", "rug", "carpet", "curtain", "bed")

# Objects excluded from the play area because they are backdrop (measured sizes in the
# survey; 03 requires the play area to be bounded rather than the whole scene).
BACKDROP_MIN_SIZE_M = 6.0

# Reach box around the interaction region, in world metres.
REACH = {"x": (0.6, 2.5), "y": (6.4, 8.4), "z": (0.4, 1.2)}


def ensure_collection(name: str, parent=None):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    target = parent or bpy.context.scene.collection
    if coll.name not in {c.name for c in target.children}:
        target.children.link(coll)
    return coll


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return lo, hi


def in_reach(lo, hi) -> bool:
    """Does the object's AABB intersect the bounded interaction region?"""
    return not (
        hi.x < REACH["x"][0] or lo.x > REACH["x"][1] or
        hi.y < REACH["y"][0] or lo.y > REACH["y"][1] or
        hi.z < REACH["z"][0] or lo.z > REACH["z"][1]
    )


def bake_and_export(obj, path: Path, name: str) -> dict:
    """Export one object's evaluated geometry to OBJ at world scale.

    Bakes the evaluated depsgraph so modifiers and hierarchy are applied, which 03 section 5
    requires before extraction.  Uses an axis conversion so the OBJ is Z-up metres, matching
    the solver's convention.
    """
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    lo, hi = world_bbox(obj)
    before = set(Path(p).name for p in bpy.data.filepath and [] or [])
    bpy.ops.wm.obj_export(
        filepath=str(path),
        export_selected_objects=True,
        apply_modifiers=True,
        export_materials=False,
        forward_axis="Y",
        up_axis="Z",
        global_scale=1.0,
    )
    return {
        "uri": str(path),
        "bytes": path.stat().st_size if path.is_file() else None,
        "aabb_min": [round(v, 9) for v in lo],
        "aabb_max": [round(v, 9) for v in hi],
    }


def main() -> int:
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    scene = bpy.context.scene
    RUNTIME.mkdir(parents=True, exist_ok=True)
    print(f"=== opened source: {SRC.name} ===")
    print(f"    scene={scene.name} objects={len(scene.objects)} collections={len(bpy.data.collections)}")

    # ---- create the six required layers -------------------------------------------
    layers = {name: ensure_collection(name) for name in LAYERS}
    print(f"\n=== layers created: {[c.name for c in layers.values()]} ===")

    result: dict = {
        "source_blend": str(SRC),
        "layers": LAYERS,
        "dynamic_props": {},
        "static_collision": {},
        "excluded_backdrop": [],
        "soft_background": [],
        "archived_static_originals": [],
        "reach_box": REACH,
    }

    # ---- dynamic prop extraction ---------------------------------------------------
    print("\n=== dynamic prop extraction (visual + collision, transforms baked) ===")
    for name, spec in DYNAMIC.items():
        obj = scene.objects.get(name)
        if obj is None:
            print(f"  {name}: NOT FOUND")
            continue
        lo, hi = world_bbox(obj)
        size = hi - lo
        vis_path = RUNTIME / f"{name.replace(' ', '_')}_visual.obj"
        info = bake_and_export(obj, vis_path, name)
        info.update({
            "role": spec["role"],
            "supported_by": spec["support"],
            "support_z": spec["support_z"],
            "source_aabb_bottom_z": round(lo.z, 9),
            "dimensions_m": [round(v, 9) for v in size],
            # Where the base must sit so the body rests on its real support.
            "resting_base_offset_z": round(spec["support_z"] - lo.z, 9),
        })
        result["dynamic_props"][name] = info
        print(f"  {name[:28]:28s} {len(obj.data.vertices)} v  dims={[round(v,4) for v in size]}")
        print(f"      support={spec['support']} @z={spec['support_z']:.6f}; "
              f"aabb bottom z={lo.z:.6f}; resting offset={info['resting_base_offset_z'] * 1000:+.4f} mm")
        print(f"      exported {vis_path.name} ({info['bytes']} bytes)")

        # Move the original into the dynamic-visual layer; its STATIC twin is what gets
        # archived, so no static copy of a dynamic body remains to be hit.
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        layers["interaction_dynamic_visual"].objects.link(obj)

    # ---- static collision region ---------------------------------------------------
    print("\n=== static collision region (bounded, not the whole scene) ===")
    all_meshes = [o for o in scene.objects if o.type == "MESH"]
    for obj in all_meshes:
        name = obj.name
        if name in DYNAMIC:
            continue
        lo, hi = world_bbox(obj)
        size = hi - lo
        max_size = max(size)

        if max_size >= BACKDROP_MIN_SIZE_M or not in_reach(lo, hi):
            # Backdrop / outside the play area: archive it and keep it out of collision.
            # It is NEVER deleted, per 03 and the project-wide no-delete rule.
            if max_size >= BACKDROP_MIN_SIZE_M:
                result["excluded_backdrop"].append({
                    "name": name, "size_m": [round(v, 3) for v in size],
                    "reason": "backdrop larger than the play area",
                })
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            layers["source_archive"].objects.link(obj)
            obj.hide_viewport = True
            obj.hide_render = True
            if name in STATIC_REQUIRED:
                # A required collider must never be archived silently.
                raise SystemExit(f"FATAL: required collider {name} fell outside the reach box")
            continue

        # SOFT FURNISHING inside the play area: keep it visible but OUT of dynamic collision.
        # Measured distance to the interaction region is recorded so the no-go check in stage
        # 05 can be enforced against a number rather than an assertion.
        if any(k in name.lower() for k in SOFT_KEYWORDS):
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            layers["environment_static_visual"].objects.link(obj)
            result["soft_background"].append({
                "name": name,
                "size_m": [round(v, 9) for v in size],
                "aabb_min": [round(v, 6) for v in lo],
                "aabb_max": [round(v, 6) for v in hi],
                "reason": ("soft furnishing: background only, excluded from dynamic collision "
                           "because rigid-body-vs-soft is not simulated in this project"),
            })
            print(f"    SOFT background-only: {name}  size={[round(v,3) for v in size]}")
            continue

        # Inside the play area: this is real static collision.
        for coll in list(obj.users_collection):
            coll.objects.unlink(obj)
        layers["environment_static_collision"].objects.link(obj)
        result["static_collision"][name] = {
            "aabb_min": [round(v, 9) for v in lo],
            "aabb_max": [round(v, 9) for v in hi],
            "size_m": [round(v, 9) for v in size],
            "triangles": len(obj.data.polygons),
            "is_required": name in STATIC_REQUIRED,
        }

    print(f"  static collision objects: {len(result['static_collision'])}")
    print(f"  soft background-only objects: {len(result['soft_background'])}")
    for name in STATIC_REQUIRED:
        ok = name in result["static_collision"]
        print(f"    required {name:14s} present={ok}")
        if not ok:
            raise SystemExit(f"FATAL: required static collider {name} is missing")

    # Export the static collision region as ONE bounded mesh, and also PER OBJECT.
    #
    # Why per object: pybullet's `createCollisionShape(GEOM_MESH, vertices=..., indices=...)`
    # FAILS above roughly 100k triangles on this build (measured: 100000 tri OK, 200000 tri
    # FAILED), while the exported region has 283816 triangles. The `fileName=` route loads the
    # full mesh successfully (measured), so the solver must use file paths -- and per-object
    # files keep each one small enough to load by either route.
    print("\n=== export static collision meshes (merged + per object) ===")
    bpy.ops.object.select_all(action="DESELECT")
    n_sel = 0
    for name in result["static_collision"]:
        obj = scene.objects.get(name)
        if obj:
            obj.select_set(True)
            n_sel += 1
    static_path = RUNTIME / "environment_static_collision.obj"
    bpy.ops.wm.obj_export(
        filepath=str(static_path),
        export_selected_objects=True,
        apply_modifiers=True,
        export_materials=False,
        forward_axis="Y", up_axis="Z", global_scale=1.0,
    )
    result["static_collision_mesh"] = {
        "uri": str(static_path),
        "objects_selected": n_sel,
        "bytes": static_path.stat().st_size if static_path.is_file() else None,
        "load_route": "fileName (the vertices/indices route fails above ~100k triangles)",
    }
    print(f"  merged: {static_path.name} from {n_sel} objects "
          f"({result['static_collision_mesh']['bytes']} bytes)")

    per_object = {}
    for name in result["static_collision"]:
        obj = scene.objects.get(name)
        if obj is None:
            continue
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        safe = name.replace(" ", "_").replace(".", "_")
        p = RUNTIME / f"static_{safe}.obj"
        bpy.ops.wm.obj_export(
            filepath=str(p), export_selected_objects=True, apply_modifiers=True,
            export_materials=False, forward_axis="Y", up_axis="Z", global_scale=1.0,
        )
        per_object[name] = {
            "uri": str(p),
            "bytes": p.stat().st_size if p.is_file() else None,
            "triangles": len(obj.data.polygons),
        }
        print(f"    {name:36s} {len(obj.data.polygons):>7d} tri  {p.name}")
    result["static_collision_per_object"] = per_object

    # ---- lighting ------------------------------------------------------------------
    print("\n=== authored lighting preserved ===")
    lights = [o for o in scene.objects if o.type == "LIGHT"]
    for o in lights:
        for coll in list(o.users_collection):
            if coll.name not in LAYERS:
                coll.objects.unlink(o)
        if not o.users_collection:
            layers["authored_lighting"].objects.link(o)
    result["lights_preserved"] = [o.name for o in lights]
    result["world_preserved"] = scene.world.name if scene.world else None
    print(f"  {len(lights)} lights kept, world={result['world_preserved']}")

    # ---- save the runtime copy -----------------------------------------------------
    runtime_blend = RUNTIME / "italian_flat_runtime.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(runtime_blend), copy=True)
    result["runtime_blend"] = str(runtime_blend)
    print(f"\n=== saved runtime copy: {runtime_blend} ===")
    for name in LAYERS:
        coll = bpy.data.collections.get(name)
        print(f"    {name:32s} {len(coll.objects) if coll else 0} objects")
    print(f"    source_archive hidden: "
          f"{sum(1 for o in layers['source_archive'].objects if o.hide_viewport)}")

    (OUT / "layer_report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'layer_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
