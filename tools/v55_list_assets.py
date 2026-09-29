"""V5.5 stage 05: list the approved triggers actually available, with measured mass and proxy."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
GSO = ROOT / "models/gso"


def load_obj(path: Path):
    vs, fs = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                vs.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    fs.append((idx[0] - 1, idx[k] - 1, idx[k + 1] - 1))
    return np.asarray(vs, float), np.asarray(fs, np.int64)


def volume(V, F) -> float:
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    return float(abs(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0)


print("=" * 100)
print("=== approved GSO assets: proxy, dimensions, enclosed volume ===")
rows = []
for d in sorted(GSO.iterdir()):
    if not d.is_dir():
        continue
    cg = d / "collision_geometry.obj"
    if not cg.is_file():
        continue
    V, F = load_obj(cg)
    dims = (V.max(axis=0) - V.min(axis=0))
    vol = volume(V, F)
    rows.append((d.name, len(V), len(F), dims, vol))
    print(f"  {d.name:46s} {len(V):5d} v {len(F):5d} t  dims "
          f"[{dims[0]:.4f} {dims[1]:.4f} {dims[2]:.4f}]  vol {vol*1e6:8.2f} cm^3")

print("\n" + "=" * 100)
print("=== stage-03 proxy decisions (the approved dynamic assets) ===")
pd = PROPS / "proxy_decision.json"
if pd.is_file():
    dec = json.loads(pd.read_text(encoding="utf-8"))
    for k, v in dec.items():
        print(f"  {k}: chosen={v.get('chosen')} tris={v.get('triangles')} "
              f"dims={[round(x,6) for x in v.get('dimensions_m', [])]}")
        for kk in ("mass_kg", "mass_basis", "collider_type", "proxy_vs_visual_mm"):
            if kk in v:
                print(f"      {kk}: {v[kk]}")
else:
    print(f"  not found: {pd}")

print("\n" + "=" * 100)
print("=== every file under the props tree ===")
for p in sorted(PROPS.rglob("*")):
    if p.is_file():
        print(f"  {p.relative_to(PROPS)}  {p.stat().st_size} bytes")
