"""V5.5 stage 03: inspect the candidate inventory structure, then extract the planned
interaction assets with their MEASURED dimensions.

03 names four candidates (small package, Borage bottle, Creatine can, Clue box) and
warns the Clue box at ~0.497 m is too large for a ~0.33 m side table.  Those numbers
must come from the recorded inventory rather than from memory.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INV = ROOT / "tmp" / "v5_candidate_inventory.json"

WANTED = [
    "Borage_GLA240Gamma_Tocopherol",
    "Creatine_Monohydrate",
    "Clue_Board_Game_Classic_Edition",
    "Big_Dot_Aqua_Pencil_Case",
    "Fresca_Peach_Citrus_Sparkling_Flavored_Soda_12_PK",
    "Connect_4_Launchers",
]


def shape(obj, path: str = "", depth: int = 0, max_depth: int = 3) -> None:
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        print(f"{path or '<root>'} dict keys={list(obj.keys())[:14]}")
        for key, value in list(obj.items())[:4]:
            shape(value, f"{path}.{key}", depth + 1, max_depth)
    elif isinstance(obj, list):
        print(f"{path} list[{len(obj)}]")
        if obj:
            shape(obj[0], f"{path}[0]", depth + 1, max_depth)
    else:
        print(f"{path} = {str(obj)[:80]}")


def find_records(obj):
    """Depth-first search for the first list of dicts that looks like asset records."""
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        keys = set(obj[0].keys())
        if keys & {"name", "id", "asset", "path", "mesh"}:
            return obj
    if isinstance(obj, dict):
        for value in obj.values():
            found = find_records(value)
            if found:
                return found
    if isinstance(obj, list):
        for value in obj:
            found = find_records(value)
            if found:
                return found
    return None


def main() -> int:
    data = json.loads(INV.read_text(encoding="utf-8"))
    print("=== structure ===")
    shape(data)
    print()

    records = find_records(data)
    if not records:
        print("no asset-record list found")
        return 1

    print(f"=== {len(records)} asset records; keys: {sorted(records[0].keys())} ===")
    print()

    hit = 0
    for record in records:
        name = str(record.get("name") or record.get("id") or record.get("asset") or "")
        if not any(w.lower() in name.lower() for w in WANTED):
            continue
        hit += 1
        print(f"=== {name} ===")
        for key in sorted(record.keys()):
            value = record[key]
            text = str(value)
            if len(text) > 200:
                if isinstance(value, list):
                    print(f"    {key}: list[{len(value)}] head={str(value[:6])[:150]}")
                elif isinstance(value, dict):
                    print(f"    {key}: dict keys={sorted(value.keys())[:14]}")
                else:
                    print(f"    {key}: <{len(text)} chars>")
            else:
                print(f"    {key}: {value}")
        print()

    if not hit:
        print("none of the wanted assets were found by name; listing all names:")
        for record in records[:60]:
            print("   ", record.get("name") or record.get("id"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
