"""List what the striker asset actually contains, so its RENDER mesh can be identified.

The solver used `collision_geometry.obj`. The render needs the visual mesh, and they are different
files: the collision proxy is 124 triangles while the visual one is the full scan. Rendering the
collision proxy would deliver a video of a low-poly block, so the visual path must be found and its
size recorded.
"""

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
DIR = GSO / "Creatine_Monohydrate"

print("=" * 100)
print(f"=== {DIR} ===")
print(f"exists: {DIR.is_dir()}")
if DIR.is_dir():
    for p in sorted(DIR.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(DIR).as_posix():56s} {p.stat().st_size:>12d} B")

print("\n=== the same for two other assets, to see the expected layout ===")
others = sorted(d for d in GSO.iterdir() if d.is_dir() and d.name != "Creatine_Monohydrate")[:3]
for d in others:
    print(f"\n  {d.name}:")
    for p in sorted(d.rglob("*")):
        if p.is_file():
            print(f"    {p.relative_to(d).as_posix():54s} {p.stat().st_size:>12d} B")

print("\n=== total assets under models/gso ===")
print(f"  {len([d for d in GSO.iterdir() if d.is_dir()])} directories")
