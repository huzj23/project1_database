"""Find the `vase` 05 section 4 names as the sanctioned fallback, and any kitchen table."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"

# Look through every JSON under the scene tree for object inventories.
print("=" * 96)
print("=== scene JSON files ===")
for p in sorted(SCENES.rglob("*.json")):
    print(f"  {p.relative_to(SCENES)}  {p.stat().st_size} bytes")

print("\n" + "=" * 96)
print("=== objects whose name matches vase / vaso / kitchen / cucina ===")
KEYS = ("vase", "vaso", "kitchen", "cucina", "fioriera", "jar", "bottle", "vassoio")
for p in sorted(SCENES.rglob("*.json")):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  {p.name}: unreadable ({e})")
        continue
    found = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(k, str) and any(t in k.lower() for t in KEYS):
                    found.append(f"{path}/{k}")
                walk(v, f"{path}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node[:4000]):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            if any(t in node.lower() for t in ("vase", "vaso", "cucina", "fioriera")):
                found.append(f"{path} = {node!r}")
    walk(d)
    if found:
        print(f"\n  {p.relative_to(SCENES)}:")
        for f in found[:40]:
            print(f"    {f}")
