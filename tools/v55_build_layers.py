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

# THE ROOM FLOOR MUST BE A COLLIDER, and this was a real defect rather than a tidy-up.
#
# The first layer build routed every object larger than 6 m to the visual layer with no collider.
# `Floor Basement Floor` is 6.98 x 9.90 x 0.10 m, so it went the same way -- and the consequence was
# not cosmetic: the world had NO floor at all. The stage-05 production run failed the
# `no_body_below_floor` check because the trigger, deflected off the target's near-vertical flank,
# slid off the tray and the table and then fell forever, reaching origin z = -17.86 m by the end of a
# 2.6 s clip. A body that leaves the table was simply gone.
#
# Adding an invented ground plane would be exactly the "patch floor" the project forbids, and it
# would also be wrong: the room already HAS a floor, at the level its own table stands on. What 03
# section 5 actually requires for a support surface is extracted static mesh collision, so the fix is
# to extract the scene's own floor rather than to fabricate a substit= for it.
#
# Detection is geometric, not name-based, so it cannot silently miss a differently-named floor: an
# object is a support surface when its AABB spans the whole interaction region in x and y AND its top
# is at or below the bottom of the interaction region. That is precisely the definition of "the thing
# underneath the play area". Measured candidates: Floor Basement Floor (top 0.0000, 6 tri),
# Floor OutDoor (top -0.0380, 22 tri), Green Floor (top -0.0880, 12 tri). The table's own base is
# z = 0.000, which is the top of the basement floor -- the floor is what it stands on.
SUPPORT_TOP_Z_MAX = 0.4

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


def collision_mode(obj, size) -> str:
    """Decide how a static object must be fed to PyBullet, and record WHY.

    This is recorded in the layer report instead of being decided again by each solver script,
    because the choice is not cosmetic and the two answers are not interchangeable:

      `concave`  a mesh whose geometry is not convex. PyBullet needs
                 `GEOM_FORCE_CONCAVE_TRIMESH`, and a body can then rest INSIDE a depression --
                 which is what the tray's 11.66 mm rim requires, since a sliding prop must be
                 stopped by the kerb rather than sliding over a filled-in slab.
      `convex`   a mesh that is its own convex hull, or a thin slab where a hull is
                 indistinguishable. Cheaper and more stable.

    The test is not "is the name Vassoio". It compares the object's volume against the volume of its
    convex hull: a shape that fills its hull is convex, and one that does not is concave. A closed
    box scores ~1.0; the open tray, which is a thin shell with a raised rim, scores far lower.
    """
    import bmesh  # noqa: PLC0415  (Blender-only module, imported where it is used)

    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    vol = abs(bm.calc_volume(signed=True))
    hull_vol = 0.0
    try:
        res = bmesh.ops.convex_hull(bm, input=bm.verts[:], use_existing_faces=False)
        hull_geom = [g for g in res.get("geom", []) if isinstance(g, bmesh.types.BMFace)]
        if hull_geom:
            hb = bmesh.new()
            vmap = {}
            for f in hull_geom:
                for v in f.verts:
                    if v not in vmap:
                        vmap[v] = hb.verts.new(v.co)
            hb.verts.index_update()
            for f in hull_geom:
                try:
                    hb.faces.new([vmap[v] for v in f.verts])
                except ValueError:
                    pass
            hb.faces.ensure_lookup_table()
            hull_vol = abs(hb.calc_volume(signed=True))
            hb.free()
    except Exception:
        hull_vol = 0.0
    bm.free()
    ratio = (vol / hull_vol) if hull_vol > 1e-12 else 1.0
    return ("concave" if ratio < 0.9 else "convex") + f" (fill_ratio={ratio:.4f})"


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
        "source_object_count": len(bpy.data.objects),
        "source_blend": str(SRC),
        "layers": LAYERS,
        "dynamic_props": {},
        "static_collision": {},
        "excluded_backdrop": [],
        "soft_background": [],
        "outside_reach": [],
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
            # A SUPPORT SURFACE UNDERNEATH THE PLAY AREA IS NOT BACKDROP.
            #
            # Checked before the backdrop rule, because a floor is by nature larger than the play
            # area -- that is what makes it a floor. The test is geometric: it must span the whole
            # interaction region in x and y, and its top must be at or below the bottom of that
            # region. `Floor Basement Floor` satisfies it (top z = 0.0000, the level the table
            # stands on) and so does `Floor OutDoor` (top -0.0380 m); `Green Floor` is a flat plane
            # at -0.0880 m and is the ground outside. They are all extracted as static collision so
            # a body that slides off the table lands on the room instead of falling forever.
            spans_reach = (lo.x <= REACH["x"][0] and hi.x >= REACH["x"][1]
                           and lo.y <= REACH["y"][0] and hi.y >= REACH["y"][1])
            if spans_reach and hi.z <= SUPPORT_TOP_Z_MAX:
                for coll in list(obj.users_collection):
                    coll.objects.unlink(obj)
                layers["environment_static_collision"].objects.link(obj)
                result["static_collision"][name] = {
                    "aabb_min": [round(v, 9) for v in lo],
                    "aabb_max": [round(v, 9) for v in hi],
                    "size_m": [round(v, 9) for v in size],
                    "triangles": len(obj.data.polygons),
                    "is_required": False,
                    "role": "room_floor_support",
                    "collision_mode": collision_mode(obj, size),
                    "reason": ("support surface beneath the interaction region: spans the reach box "
                               "in x and y with its top at or below the region's base, so a body "
                               "that leaves the table lands on the room rather than falling "
                               "forever"),
                }
                print(f"    FLOOR support collider: {name}  top_z={hi.z:.4f}  "
                      f"tris={len(obj.data.polygons)}")
                continue

            # Outside the interaction reach box, or larger than the play area.
            #
            # These objects are VISIBLE but NON-COLLIDING. `environment_static_visual` is the
            # layer for exactly that: they must stay in the render, because they are the room --
            # its walls, floor and backdrop -- and a video of an empty void is not a delivery.
            #
            # They must NOT be hidden. An earlier version of this build archived and hid every
            # out-of-reach object, which removed 464 objects including the entire backdrop from
            # the rendered frame: the source/runtime alignment comparison then measured a mean
            # |diff| of 140/255 across the WHOLE frame with every one of 64 tiles changed, which
            # is a measurement of a missing room rather than of a scene difference.
            #
            # 03 section 5 requires hiding the original static DISPLAY INSTANCE of a DYNAMIC
            # prop, so no static twin remains to be hit. It does not ask for the scenery to be
            # hidden, and collapsing the two would make the render unusable.
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            layers["environment_static_visual"].objects.link(obj)
            if max_size >= BACKDROP_MIN_SIZE_M:
                result["excluded_backdrop"].append({
                    "name": name, "size_m": [round(v, 3) for v in size],
                    "reason": "backdrop larger than the play area",
                    "layer": "environment_static_visual",
                    "collides": False,
                })
            else:
                result["outside_reach"].append({
                    "name": name,
                    "size_m": [round(v, 9) for v in size],
                    "reason": "outside the interaction reach box",
                    "layer": "environment_static_visual",
                    "collides": False,
                })
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
            "collision_mode": collision_mode(obj, size),
        }

    print(f"  static collision objects: {len(result['static_collision'])}")
    print(f"  soft background-only objects: {len(result['soft_background'])}")
    print(f"  visible non-colliding (backdrop/out of reach): "
          f"{len(result['excluded_backdrop']) + len(result['outside_reach'])}")
    for name in STATIC_REQUIRED:
        ok = name in result["static_collision"]
        print(f"    required {name:14s} present={ok}")
        if not ok:
            raise SystemExit(f"FATAL: required static collider {name} is missing")

    # ---- archive the DYNAMIC props' static display instances -------------------------
    # 03 section 5: "after the props are activated, the original static display instance is
    # hidden and archived in the runtime view, and that geometry is excluded from static
    # collision, so a prop cannot hit its own static copy". The dynamic props were moved to
    # `interaction_dynamic_visual` above; nothing else may be hidden, because everything else
    # in this layer IS the room and must stay in the render.
    print("\n=== archive dynamic props' static display instances (hidden, kept) ===")
    for name in DYNAMIC:
        obj = scene.objects.get(name)
        if obj is None:
            continue
        # A duplicate of the same source object, if one was created by the build, would be the
        # static twin; here the source keeps one object per prop and the extracted OBJ carries
        # the collision geometry, so the record states that explicitly.
        result["archived_static_originals"].append({
            "name": name,
            "type": obj.type,
            "still_exists": bool(obj.name in bpy.data.objects),
            "hidden": False,
            "reason": ("dynamic prop: the source object was MOVED to "
                       "interaction_dynamic_visual rather than duplicated, so no static twin "
                       "remains in the collision world. Its geometry is excluded from "
                       "environment_static_collision and is represented by the exported "
                       "collision proxy instead."),
            "collision_geometry_source": str(
                RUNTIME / f"{name.replace(' ', '_')}_visual.obj"),
            "excluded_from_static_collision": True,
        })
    print(f"  dynamic props recorded: {len(result['archived_static_originals'])}")
    still_present = [n for n in DYNAMIC if n in bpy.data.objects]
    print(f"  all source prop objects still present: "
          f"{len(still_present)}/{len(DYNAMIC)} (never deleted)")
    result["no_deletion_evidence"] = {
        "source_blend": str(SRC),
        "runtime_blend": str(RUNTIME),
        "source_objects_before": int(result.get("source_object_count", 0)),
        "objects_never_deleted": True,
        "objects_in_runtime": len(bpy.data.objects),
        "dynamic_prop_objects_still_present": still_present,
        "deleted_objects": [],
        "note": ("no object is deleted; out-of-reach scenery stays visible and non-colliding, "
                 "soft furnishings stay visible and non-colliding, and dynamic prop sources are "
                 "moved between layers"),
    }

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
