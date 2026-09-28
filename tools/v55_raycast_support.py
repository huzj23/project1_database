"""V5.5 stage 05 section 1: determine the bottle's REAL support by mesh raycast.

05 section 1 is explicit: the AABB-inferred support relation is only a candidate, and
"mesh raycasts and the visual image must determine whether the bottle rests on the tray, the
table top, or some other geometry". The survey already showed something that cannot be
taken at face value: the tray `Vassoio` spans z 0.5000-0.5223 while the bottle's AABB bottom
is 0.5092, i.e. INSIDE the tray's bounding box. Either the tray has a raised rim and a lower
floor, or the AABB is misleading.

This casts rays straight down through each prop's own footprint and reports every surface it
crosses, so the true support is identified from geometry rather than inferred.

Also determines, per 05 section 2.3, whether the bottle's cap `Tappo Cristallo` is actually
attached: if the cap is a separate resting object, welding it to the bottle would be
physically unjustified, and 05 forbids that ("cannot look loose but be welded with no
reason").

Run with Blender in background mode.  READ-ONLY.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

SRC = Path(r"D:\workspace\project1_database\models\backgrounds\candidates\italian_flat\source\flat-archiviz.blend")
OUT = Path(r"D:\workspace\project1_database\outcomes\v55\scenes")

PROPS = ["Bottiglia Cristallo", "Bicchiere Cristallo", "Bicchiere Cristallo.001",
         "Tappo Cristallo", "Vassoio", "Table", "Table.001"]


def world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    return lo, hi


def raycast_down(scene, x: float, y: float, z_start: float, depsgraph):
    """Cast straight down; return the first hit object, z, and normal."""
    origin = Vector((x, y, z_start))
    direction = Vector((0.0, 0.0, -1.0))
    hit, loc, normal, index, obj, matrix = scene.ray_cast(depsgraph, origin, direction)
    if not hit:
        return None
    return {
        "object": obj.name if obj else None,
        "z": round(loc.z, 9),
        "normal_z": round(normal.z, 6),
        "is_horizontal": bool(abs(normal.z) > 0.9),
    }


def main() -> int:
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()

    report: dict = {"source": str(SRC), "props": {}}

    print("=== downward raycasts through each prop's footprint centre ===")
    for name in PROPS:
        obj = scene.objects.get(name)
        if obj is None:
            print(f"  {name}: NOT FOUND")
            continue
        lo, hi = world_bbox(obj)
        cx, cy = (lo.x + hi.x) / 2.0, (lo.y + hi.y) / 2.0
        top = hi.z
        print(f"\n--- {name} ---")
        print(f"  aabb z {lo.z:.6f} .. {hi.z:.6f}   centre xy ({cx:.4f}, {cy:.4f})")

        # Cast from above the prop, so the prop's own top is the first hit, then continue
        # below it to find what actually supports it.
        hits = []
        z = top + 0.05
        for _ in range(8):
            h = raycast_down(scene, cx, cy, z, depsgraph)
            if h is None:
                break
            hits.append(h)
            print(f"    hit {h['object']:28s} z={h['z']:.6f} normal_z={h['normal_z']:.4f} "
                  f"horizontal={h['is_horizontal']}")
            z = h["z"] - 1e-4
            if len(hits) >= 6:
                break

        # Multi-point sampling across the footprint, to see whether the support varies,
        # which is how a rimmed tray reveals itself.
        samples = []
        for fx in (-0.4, 0.0, 0.4):
            for fy in (-0.4, 0.0, 0.4):
                sx = cx + fx * (hi.x - lo.x) / 2.0
                sy = cy + fy * (hi.y - lo.y) / 2.0
                h = raycast_down(scene, sx, sy, top + 0.05, depsgraph)
                samples.append({
                    "offset": [fx, fy],
                    "first_hit": h["object"] if h else None,
                    "z": h["z"] if h else None,
                })
        distinct = sorted({s["first_hit"] for s in samples if s["first_hit"]})
        print(f"  first surface across the footprint: {distinct}")
        for s in samples:
            print(f"    offset({s['offset'][0]:+.1f},{s['offset'][1]:+.1f}) -> "
                  f"{s['first_hit']} z={s['z']}")

        report["props"][name] = {
            "aabb_min": [round(v, 9) for v in lo],
            "aabb_max": [round(v, 9) for v in hi],
            "centre_xy": [round(cx, 9), round(cy, 9)],
            "downward_hits": hits,
            "footprint_samples": samples,
            "first_surfaces": distinct,
        }

    # ---- cap attachment: is Tappo inside / touching the bottle? --------------------
    print("\n=== cap attachment analysis (05 section 2.3) ===")
    bottle = scene.objects.get("Bottiglia Cristallo")
    cap = scene.objects.get("Tappo Cristallo")
    if bottle and cap:
        blo, bhi = world_bbox(bottle)
        clo, chi = world_bbox(cap)
        gap = clo.z - bhi.z
        overlap_z = min(bhi.z, chi.z) - max(blo.z, clo.z)
        print(f"  bottle z {blo.z:.6f} .. {bhi.z:.6f}")
        print(f"  cap    z {clo.z:.6f} .. {chi.z:.6f}")
        print(f"  vertical gap between cap bottom and bottle top: {gap * 1000:.4f} mm")
        print(f"  vertical overlap: {overlap_z * 1000:.4f} mm")
        cap_centre = (clo + chi) / 2.0
        bottle_centre = (blo + bhi) / 2.0
        print(f"  horizontal centre offset: "
              f"{((cap_centre.x - bottle_centre.x) ** 2 + (cap_centre.y - bottle_centre.y) ** 2) ** 0.5 * 1000:.4f} mm")
        report["cap_analysis"] = {
            "bottle_z": [round(blo.z, 9), round(bhi.z, 9)],
            "cap_z": [round(clo.z, 9), round(chi.z, 9)],
            "vertical_gap_m": round(gap, 9),
            "vertical_overlap_m": round(overlap_z, 9),
            "horizontal_centre_offset_m": round(
                ((cap_centre.x - bottle_centre.x) ** 2 +
                 (cap_centre.y - bottle_centre.y) ** 2) ** 0.5, 9),
            "interpretation": (
                "cap sits ON the bottle's top surface, so treating the pair as one declared "
                "rigid assembly is physically justified"
                if gap < 0.01 else
                "cap is separated from the bottle; welding it would be unjustified"
            ),
        }
        print(f"  -> {report['cap_analysis']['interpretation']}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "italian_flat_support_raycast.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'italian_flat_support_raycast.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
