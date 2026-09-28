"""V5.5 stage 05: are the prop and static meshes in the SAME coordinate frame?

The props still free-fall even after adding `recentre_offset_m` back, and the harness's own
mesh-on-plane check reported an unexpected result, so the numbers are read out rather than
reasoned about:

  * the offset recorded for each prop,
  * the LOCAL-frame bounds of each prop mesh,
  * the WORLD-frame bounds restored by adding the offset,
  * the WORLD bounds of every static collider mesh,
  * whether the restored prop footprint actually sits over the table/tray.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
PROPS = SCENES / "props"
RUNTIME = SCENES / "runtime"


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


dec_path = PROPS / "proxy_decision.json"
print(f"proxy_decision.json exists: {dec_path.is_file()}")
dec = json.loads(dec_path.read_text(encoding="utf-8")) if dec_path.is_file() else {}
print(f"keys: {sorted(dec.keys()) if dec else 'NONE'}")

for name in ("bottle_assembly", "glass_a", "glass_b"):
    d = dec.get(name, {})
    print("=" * 74)
    print(f"== {name}")
    print(f"   chosen             : {d.get('chosen')}")
    print(f"   recentre_offset_m  : {d.get('recentre_offset_m')}")
    print(f"   world_aabb_min     : {d.get('world_aabb_min')}")
    print(f"   world_aabb_max     : {d.get('world_aabb_max')}")
    off = np.asarray(d.get("recentre_offset_m", [0.0, 0.0, 0.0]), float)

    for label, sub in (("vhacd", "vhacd"), ("hull", "hull"), ("visual", "visual")):
        files = sorted((PROPS / name / sub).glob("*.obj"))
        if not files:
            print(f"   {label}: no files")
            continue
        vs = [load_obj(f)[0] for f in files]
        V = np.vstack(vs)
        lo, hi = V.min(axis=0), V.max(axis=0)
        wlo, whi = lo + off, hi + off
        print(f"   {label:6s} local z {lo[2]:+.6f}..{hi[2]:+.6f} | "
              f"xyz {np.round(lo, 4)} .. {np.round(hi, 4)}")
        print(f"          +offset -> world z {wlo[2]:.6f}..{whi[2]:.6f} | "
              f"xyz {np.round(wlo, 4)} .. {np.round(whi, 4)}")

print("=" * 74)
print("== static colliders (already in world coordinates) ==")
for p in sorted(RUNTIME.glob("static_*.obj")):
    V, F = load_obj(p)
    lo, hi = V.min(axis=0), V.max(axis=0)
    print(f"   {p.name:52s} z {lo[2]:.6f}..{hi[2]:.6f}")
    print(f"        x {lo[0]:.4f}..{hi[0]:.4f}  y {lo[1]:.4f}..{hi[1]:.4f}")

print("=" * 74)
print("== does the restored prop footprint sit over a static object? ==")
# The tray Vassoio floor was measured at z=0.510600 and its rim at 0.522260.
for name in ("bottle_assembly", "glass_a", "glass_b"):
    d = dec.get(name, {})
    off = np.asarray(d.get("recentre_offset_m", [0.0, 0.0, 0.0]), float)
    files = sorted((PROPS / name / "vhacd").glob("*.obj"))
    if not files:
        continue
    V = np.vstack([load_obj(f)[0] for f in files]) + off
    lo, hi = V.min(axis=0), V.max(axis=0)
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    print(f"   {name:18s} centre xy ({cx:.4f}, {cy:.4f})  z base {lo[2]:.6f}")
    vp = RUNTIME / "static_Vassoio.obj"
    if vp.is_file():
        vv, _ = load_obj(vp)
        vlo, vhi = vv.min(axis=0), vv.max(axis=0)
        inside = (vlo[0] <= cx <= vhi[0]) and (vlo[1] <= cy <= vhi[1])
        print(f"        tray x {vlo[0]:.4f}..{vhi[0]:.4f} y {vlo[1]:.4f}..{vhi[1]:.4f} "
              f"-> prop centre over tray: {inside}")
