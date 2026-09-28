"""V5.5 stage 03 (today's work order): determine the real-world scale of each source scene, so the new
body placement and any collider building can happen in METRES.

Why this gate comes first
-------------------------
02's contract fixes units as metres, and 03 says the source numbers must not be treated
as metres directly.  The measured facts make the danger concrete:

    italian_flat  scale_length =  1.0   bbox  ~12.5 x 23.7 x 7.5
    the_shed      scale_length =  1.0   bbox  ~24.2 x 22.9 x 19.8
    hidden_alley  scale_length = 10.0   bbox ~1227 x 1227 x 1240   <-- clearly not metres

A naive import would put a 0.11 m bottle into a 1227 m world, or a 1227 m wall into a
0.33 m table scene.  So this script derives the metric interpretation of each scene from
INDEPENDENT physical anchors rather than trusting scale_length alone:

  * the door height of the Italian Flat interior (a real door is ~2.0-2.1 m)
  * the table-top height (a real dining/side table is ~0.45-0.75 m)
  * the wall/board height in Hidden Alley
  * the workbench height in The Shed

and then states, with evidence, whether a global uniform scale is required and what it is.

Run with Blender (needs bpy):
    blender --background --factory-startup --python tools/v55_derive_scale.py -- --scene <name>
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path("/data/raw/huzijian/project1_database")
SOURCES_WIN = {
    "italian_flat": Path(r"D:\workspace\project1_database\models\backgrounds\candidates\italian_flat\source\flat-archiviz.blend"),
    "hidden_alley": Path(r"D:\workspace\project1_database\models\backgrounds\candidates\hidden_alley\extracted\ph_hidden_alley.blend"),
    "the_shed": Path(r"D:\workspace\project1_database\models\backgrounds\candidates\the_shed\extracted\the_shed\the_shed.blend"),
}
SOURCES_SERVER = {
    "italian_flat": ROOT / "models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend",
    "hidden_alley": ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend",
    "the_shed": ROOT / "models/backgrounds/candidates/the_shed/extracted/the_shed/the_shed.blend",
}

# Named objects that act as independent metric anchors.  Chosen because they are
# ordinary furniture with a well-known real-world size range.
ANCHORS = {
    "italian_flat": {
        "table": ["Table", "Table.001", "Table_Kitchen", "Kitchen Table"],
        "door": ["Door", "Doors", "Door.001", "Sliding Doors"],
        "bottle": ["Bottiglia Cristallo"],
        "glass": ["Bicchiere Cristallo"],
    },
    "hidden_alley": {
        "board": ["wooden_boards", "wooden_boards.001", "wooden_boards.002"],
    },
    "the_shed": {
        "table": ["WoodenTable_03", "Table", "Workbench"],
    },
}

# Real-world plausibility ranges in metres, used to judge a candidate factor.
EXPECTED = {
    "door_height_m": (1.80, 2.30),
    "table_top_height_m": (0.40, 1.00),
    "bottle_height_m": (0.15, 0.35),
    "glass_height_m": (0.06, 0.20),
    "board_height_m": (1.00, 3.20),
}


def obj_world_bbox(obj) -> tuple[Vector, Vector]:
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for corner in obj.bound_box:
        w = obj.matrix_world @ Vector(corner)
        for i in range(3):
            lo[i] = min(lo[i], w[i])
            hi[i] = max(hi[i], w[i])
    return lo, hi


def measure(name: str) -> dict:
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != "MESH":
        return {"found": False}
    lo, hi = obj_world_bbox(obj)
    size = hi - lo
    return {
        "found": True,
        "name": obj.name,
        "dimensions": [round(v, 6) for v in size],
        "height": round(size.z, 6),
        "top_z": round(hi.z, 6),
        "bottom_z": round(lo.z, 6),
        "world_location": [round(v, 6) for v in obj.matrix_world.translation],
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", required=True, choices=sorted(SOURCES_WIN))
    ap.add_argument("--side", default="server", choices=["server", "local"])
    args = ap.parse_args(argv)

    path = (SOURCES_SERVER if args.side == "server" else SOURCES_WIN)[args.scene]
    print(f"=== {args.scene} ({args.side}) ===", flush=True)
    print(f"opening {path}", flush=True)
    bpy.ops.wm.open_mainfile(filepath=str(path))

    scene = bpy.context.scene
    scale_length = scene.unit_settings.scale_length
    print(f"unit_system={scene.unit_settings.system} scale_length={scale_length}", flush=True)

    # Whole-scene bbox from raw mesh bounds (no depsgraph evaluation: it segfaults on 3.4.1).
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        try:
            olo, ohi = obj_world_bbox(obj)
            for i in range(3):
                lo[i] = min(lo[i], olo[i])
                hi[i] = max(hi[i], ohi[i])
        except Exception:
            pass
    scene_bbox = {
        "min": [round(v, 4) for v in lo],
        "max": [round(v, 4) for v in hi],
        "size": [round(hi[i] - lo[i], 4) for i in range(3)],
    }
    print(f"scene bbox size: {scene_bbox['size']}", flush=True)

    # Measure the named anchors.
    measured: dict[str, dict] = {}
    for role, names in ANCHORS.get(args.scene, {}).items():
        for name in names:
            info = measure(name)
            if info.get("found"):
                measured[f"{role}:{name}"] = info
                print(f"  {role:12s} {name:28s} h={info['height']:9.4f} "
                      f"top_z={info['top_z']:9.4f} dims={info['dimensions']}", flush=True)
    if not measured:
        print("  (no named anchors found; listing biggest meshes for manual anchor choice)",
              flush=True)
        sized = []
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            try:
                _, ohi = obj_world_bbox(obj)
                olo, _ = obj_world_bbox(obj)
                sized.append((float((ohi - olo).length), obj.name))
            except Exception:
                pass
        sized.sort(reverse=True)
        for _, name in sized[:15]:
            info = measure(name)
            print(f"    BIG {name:34s} h={info['height']:9.4f} dims={info['dimensions']}",
                  flush=True)

    # Derive the scale factor from any anchor whose real-world size we can bound.
    print()
    print("  --- scale derivation ---", flush=True)
    derivations = []
    for key, info in measured.items():
        role = key.split(":", 1)[0]
        h = info["height"]
        if h <= 0:
            continue
        if role == "door":
            target = 2.05
            rng = EXPECTED["door_height_m"]
        elif role == "table":
            target = 0.75
            rng = EXPECTED["table_top_height_m"]
        elif role == "bottle":
            target = 0.25
            rng = EXPECTED["bottle_height_m"]
        elif role == "glass":
            target = 0.12
            rng = EXPECTED["glass_height_m"]
        elif role == "board":
            target = 2.00
            rng = EXPECTED["board_height_m"]
        else:
            continue
        factor = target / h
        implied = h * factor
        derivations.append({
            "anchor": key,
            "role": role,
            "measured_height": round(h, 6),
            "assumed_real_height_m": target,
            "acceptable_range_m": list(rng),
            "required_factor": round(factor, 6),
            "implied_height_after_factor_m": round(implied, 6),
        })
        print(f"    {key:34s} h={h:9.4f} -> factor {factor:.6g} "
              f"=> {implied:.3f} m (want {target} in {rng})", flush=True)

    # scale_length itself is the DECLARED factor; report whether it agrees.
    declared = {
        "scale_length": scale_length,
        "scene_bbox_size": scene_bbox["size"],
        "note": (
            "scale_length is the scene's declared unit scale. A bbox spanning >100 units "
            "with scale_length 10 indicates the source is NOT authored in metres."
        ),
    }
    print(f"    declared scale_length = {scale_length}", flush=True)

    record = {
        "scene": args.scene,
        "side": args.side,
        "source": str(path),
        "blender": bpy.app.version_string,
        "unit_system": scene.unit_settings.system,
        "scale_length": scale_length,
        "scene_bbox": scene_bbox,
        "anchors": measured,
        "derivations": derivations,
        "declared": declared,
    }
    print("SCALE_RECORD " + json.dumps(record), flush=True)

    out_dir = Path(r"D:\workspace\project1_database\outcomes\v55\bootstrap\20260928T194500\scale") \
        if args.side == "local" else ROOT / "outcomes/v55/bootstrap/20260928T194500/scale"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.scene}_{args.side}.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
