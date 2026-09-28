"""V5.5 stage 03: pull per-object sizes out of the V5.4 Hidden Alley audit.

The audit stores its objects under `all_mesh_objects`, whose schema differs from the
generic shapes my first probe assumed.  This inspects that key directly and reports the
sizes of everyday objects whose real dimensions are known, so the scene's metric scale is
established from physical anchors rather than from a guessed scale_length convention.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "outcomes" / "v54_feasibility" / "hidden_alley_interaction_audit.json"

KNOWN = {
    "baseball_bat": 0.84,
    "boombox": 0.45,
    "barrel_stove": 1.00,
    "barrel_03": 0.90,
    "barrel": 0.90,
    "wooden_handle_saber": 0.30,
    "wooden_boards": 2.00,
}


def main() -> int:
    data = json.loads(AUDIT.read_text(encoding="utf-8"))

    for key in ("all_mesh_objects", "mesh_totals", "interpretation", "physics"):
        value = data.get(key)
        print(f"=== {key} ===")
        if isinstance(value, list):
            print(f"  list[{len(value)}]")
            if value:
                print(f"  element keys: {sorted(value[0].keys()) if isinstance(value[0], dict) else type(value[0])}")
                print(f"  first element: {json.dumps(value[0])[:600]}")
        elif isinstance(value, dict):
            print(f"  dict keys: {sorted(value.keys())[:20]}")
            print(f"  value: {json.dumps(value)[:400]}")
        else:
            print(f"  {value}")
        print()

    objects = data.get("all_mesh_objects")
    if not isinstance(objects, list):
        print("all_mesh_objects is not a list; cannot anchor")
        return 1

    print(f"=== scanning {len(objects)} mesh objects for known-size anchors ===")
    hits = 0
    for item in objects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("object") or "")
        low = name.lower()
        match = next((k for k in KNOWN if k in low), None)
        if not match:
            continue
        dims = item.get("dimensions") or item.get("dimensions_m") or item.get("size")
        bb = item.get("bbox") or item.get("bound_box") or item.get("world_bbox")
        if dims is None and isinstance(bb, dict):
            mn, mx = bb.get("min"), bb.get("max")
            if isinstance(mn, list) and isinstance(mx, list):
                dims = [float(mx[i]) - float(mn[i]) for i in range(3)]
        if not isinstance(dims, list) or len(dims) < 3:
            continue
        dims = [float(v) for v in dims[:3]]
        real = KNOWN[match]
        longest = max(dims)
        hits += 1
        print(f"  {name[:50]:50s}")
        print(f"      dims={[round(d,4) for d in dims]}  longest={longest:.4f}")
        print(f"      known real size for {match}: ~{real} m")
        if longest > 0:
            print(f"      implied factor to metres: {real / longest:.5f}")
        if hits >= 15:
            break

    if not hits:
        print("  no known-size anchor matched. Dumping the 40 largest objects:")
        sized = []
        for item in objects:
            if not isinstance(item, dict):
                continue
            dims = item.get("dimensions") or item.get("dimensions_m") or item.get("size")
            if isinstance(dims, list) and len(dims) >= 3:
                sized.append((max(float(v) for v in dims[:3]), str(item.get("name")), [round(float(v), 3) for v in dims[:3]]))
        sized.sort(reverse=True)
        for longest, name, dims in sized[:40]:
            print(f"    {longest:10.4f}  {name[:44]:44s} {dims}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
