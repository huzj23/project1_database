"""V5.5 stage 03 section 5: survey the Italian Flat table region before layering.

Layering decisions must come from measurements, not from the object list: 03 requires the
static collision world to include every wall, table leg, tray and kerb a dynamic body could
sweep into, and requires the ORIGINAL static instances of the extracted props to be hidden
and excluded from static collision so a body cannot collide with its own static copy.

This reports, around the chosen table:
  * the table's real world-space top surface (z, footprint, thickness),
  * every object intersecting that footprint or standing within reach of it,
  * which objects are the props to extract (bottle, glass),
  * the backdrop objects that must be EXCLUDED (Sky, BG_*, planes and the like),
so the extraction list and the static-collision list are both evidence-based.

Run with Blender in background mode.  READ-ONLY: never saves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SRC = Path(r"D:\workspace\project1_database\models\backgrounds\candidates\italian_flat\source\flat-archiviz.blend")
OUT = Path(r"D:\workspace\project1_database\outcomes\v55\scenes")

# Reach envelope: how far a small prop can travel from the table before it is off the table
# and no longer interesting.  Generous, so nothing that could be touched is missed.
REACH_M = 1.2


def parse_argv() -> dict:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    out = {}
    for i in range(0, len(argv) - 1, 2):
        out[argv[i].lstrip("-")] = argv[i + 1]
    return out


def world_bounds(obj) -> tuple[Vector, Vector, Vector]:
    """World-space AABB and size, from the evaluated mesh where possible."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    try:
        mesh = ev.to_mesh()
    except Exception:
        mesh = None
    if mesh is not None and len(mesh.vertices) > 0:
        mw = obj.matrix_world
        pts = [mw @ v.co for v in mesh.vertices]
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        ev.to_mesh_clear()
    else:
        # Fall back to the object's own bound box corners.
        corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
        hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return lo, hi, hi - lo


def main() -> int:
    args = parse_argv()
    scene_filter = args.get("scene")

    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    scene = bpy.context.scene
    print(f"=== scene: {scene.name} ===")
    print(f"unit_system={scene.unit_settings.system} scale_length={scene.unit_settings.scale_length}")

    # ---- locate the table objects -------------------------------------------------
    tables = [o for o in scene.objects if o.type == "MESH" and o.name.split(".")[0] in ("Table", "Tavolo")]
    if not tables:
        tables = [o for o in scene.objects if o.type == "MESH" and "table" in o.name.lower()]
    print(f"\n=== table candidates: {[t.name for t in tables]} ===")

    table_info = []
    for t in tables:
        lo, hi, size = world_bounds(t)
        top = hi.z
        # The top surface is the highest horizontal face; approximate its footprint by the
        # full AABB, then report the actual thickness from the size's smallest axis.
        table_info.append({
            "name": t.name,
            "bounds_min": [round(v, 6) for v in lo],
            "bounds_max": [round(v, 6) for v in hi],
            "size_m": [round(v, 6) for v in size],
            "top_z": round(top, 6),
            "footprint_m": [round(size.x, 6), round(size.y, 6)],
            "thinnest_axis_m": round(min(size), 6),
        })
        print(f"  {t.name:22s} top_z={top:.4f} size={[round(v,4) for v in size]} "
              f"centre=({(lo.x+hi.x)/2:.4f}, {(lo.y+hi.y)/2:.4f}, {(lo.z+hi.z)/2:.4f})")

    # The interaction table = the one whose top is a plausible standing height AND that has
    # the bottle/glass on it.  Chosen by measurement, recorded.
    if not table_info:
        print("NO TABLE FOUND")
        return 1

    # ---- find the props near each table ------------------------------------------
    print("\n=== objects standing on / near each table, within reach ===")
    all_meshes = [o for o in scene.objects if o.type == "MESH"]

    for ti in table_info:
        tlo = Vector(ti["bounds_min"])
        thi = Vector(ti["bounds_max"])
        tcentre = (tlo + thi) / 2.0
        near = []
        for o in all_meshes:
            if o.name == ti["name"] or o.name.startswith(ti["name"] + "."):
                continue
            lo, hi, size = world_bounds(o)
            c = (lo + hi) / 2.0
            horizontal = ((c.x - tcentre.x) ** 2 + (c.y - tcentre.y) ** 2) ** 0.5
            if horizontal > REACH_M:
                continue
            # Only objects whose size is prop-like at this scale, to keep the list readable.
            if max(size) > 0.6:
                continue
            near.append({
                "name": o.name,
                "size_m": [round(v, 5) for v in size],
                "centre": [round(v, 5) for v in c],
                "distance_from_table_centre_m": round(horizontal, 5),
                "bottom_z": round(lo.z, 6),
                "on_table": bool(lo.z >= ti["top_z"] - 0.02),
            })
        near.sort(key=lambda r: r["distance_from_table_centre_m"])
        print(f"\n  --- {ti['name']} (top_z={ti['top_z']:.4f}) ---")
        for r in near[:18]:
            tag = "ON TABLE" if r["on_table"] else "near/below"
            print(f"    {r['name'][:34]:34s} size={r['size_m']} dist={r['distance_from_table_centre_m']:.3f} "
                  f"bottom_z={r['bottom_z']:.4f} {tag}")
        ti["nearby"] = near

    # ---- identify what must be EXCLUDED as backdrop ------------------------------
    print("\n=== backdrop / huge objects that must be excluded from the play area ===")
    backdrop = []
    for o in all_meshes:
        lo, hi, size = world_bounds(o)
        if max(size) > 8.0:
            backdrop.append({"name": o.name, "size_m": [round(v, 3) for v in size]})
    backdrop.sort(key=lambda r: -max(r["size_m"]))
    for r in backdrop[:14]:
        print(f"    {r['name'][:40]:40s} size={r['size_m']}")

    # ---- lights / cameras / world ------------------------------------------------
    print("\n=== authored presentation ===")
    print(f"  lights : {[o.name for o in scene.objects if o.type == 'LIGHT']}")
    cams = [o for o in scene.objects if o.type == "CAMERA"]
    print(f"  cameras: {[o.name for o in cams]}")
    if scene.camera:
        print(f"  active camera: {scene.camera.name}")
    print(f"  world  : {scene.world.name if scene.world else None} "
          f"(use_nodes={scene.world.use_nodes if scene.world else None})")
    print(f"  collections: {len(bpy.data.collections)}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "italian_flat_table_survey.json").write_text(json.dumps({
        "source": str(SRC),
        "scene": scene.name,
        "unit_system": scene.unit_settings.system,
        "scale_length": scene.unit_settings.scale_length,
        "tables": table_info,
        "backdrop_objects": backdrop,
        "lights": [o.name for o in scene.objects if o.type == "LIGHT"],
        "cameras": [o.name for o in cams],
        "active_camera": scene.camera.name if scene.camera else None,
        "world": scene.world.name if scene.world else None,
        "collection_count": len(bpy.data.collections),
        "reach_envelope_m": REACH_M,
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'italian_flat_table_survey.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
