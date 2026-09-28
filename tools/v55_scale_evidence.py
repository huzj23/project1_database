"""V5.5 stage 03: establish the metric scale of the Hidden Alley scene from evidence.

The scene reports ``scale_length = 10.0`` but its own objects look metric:
``wooden_boards`` is 3.0 units tall, which is a plausible standing plank in METRES.
Resolving that contradiction matters, because treating a metric scene as decimetres (or
vice versa) would silently mis-size every collider.

The audit's ``all_mesh_objects`` entries carry ``bounds_world.dimensions``.  This script
uses them to answer two questions:

  1. Which object spans the ~1227-unit scene bbox?  If it is a backdrop/sky/ground, its
     size is irrelevant to scale and the absurd bbox is explained.
  2. What are the sizes of ordinary objects (bins, crates, chairs, barrels)?  If those
     land in normal human ranges in units, then 1 unit = 1 m and scale_length is simply a
     mis-set metadata field.

READ-ONLY.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCENES = {
    "hidden_alley": ROOT / "outcomes/v54_feasibility/hidden_alley_interaction_audit.json",
    "italian_flat": ROOT / "outcomes/v54_feasibility/italian_flat_interaction_audit.json",
}

# Objects whose real size is well known, with an acceptable metre range.
ANCHORS = {
    "wooden_boards": (1.0, 3.2, "leaning plank/board height"),
    "baseball_bat": (0.60, 1.10, "bat length"),
    "boombox": (0.25, 0.80, "boombox width"),
    "barrel_stove": (0.60, 1.60, "stove height"),
    "barrel_03": (0.60, 1.20, "barrel height"),
    "barrel_02": (0.60, 1.20, "barrel height"),
    "bottle": (0.15, 0.35, "bottle height"),
    "glass": (0.06, 0.20, "glass height"),
    "Table": (0.40, 1.00, "table height"),
    "Chair": (0.40, 1.20, "chair height"),
    "Door": (1.80, 2.40, "door height"),
}


def dims_of(item: dict):
    bb = item.get("bounds_world")
    if isinstance(bb, dict):
        d = bb.get("dimensions")
        if isinstance(d, list) and len(d) >= 3:
            return [float(v) for v in d[:3]]
    return None


def main() -> int:
    for scene, path in SCENES.items():
        if not path.is_file():
            print(f"[absent] {path}")
            continue
        print("=" * 72)
        print(f"=== {scene} ===")
        print("=" * 72)
        data = json.loads(path.read_text(encoding="utf-8"))
        objects = data.get("all_mesh_objects") or []
        print(f"mesh objects: {len(objects)}")

        sized = []
        for item in objects:
            if not isinstance(item, dict):
                continue
            d = dims_of(item)
            if d:
                sized.append((max(d), str(item.get("name", "?")), d))

        sized.sort(reverse=True)
        print(f"objects with bounds: {len(sized)}")
        print()
        print("--- 12 LARGEST objects (does a backdrop explain the huge bbox?) ---")
        for longest, name, d in sized[:12]:
            print(f"  {longest:12.3f}  {name[:44]:44s} {[round(v,3) for v in d]}")

        print()
        print("--- ANCHOR objects with known real-world size ---")
        hits = 0
        for item in objects:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", ""))
            d = dims_of(item)
            if not d:
                continue
            key = next((k for k in ANCHORS if k.lower() in name.lower()), None)
            if not key:
                continue
            lo, hi, what = ANCHORS[key]
            h = d[2]
            in_range = lo <= h <= hi
            hits += 1
            verdict = "IN RANGE as metres" if in_range else f"OUT OF RANGE ({lo}-{hi} m)"
            print(f"  {name[:40]:40s} dims={[round(v,4) for v in d]}")
            print(f"      height={h:.4f}  expected {what} {lo}-{hi} m -> {verdict}")
            if hits >= 14:
                break
        if not hits:
            print("  (no anchors matched by name)")

        # Median size of the ordinary objects, as a coarse scale sanity check.
        if sized:
            mids = sorted(d for _, _, d in sized for d in [max(d)])
            mid = mids[len(mids) // 2]
            print()
            print(f"  median longest-dimension over all meshes: {mid:.4f}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
