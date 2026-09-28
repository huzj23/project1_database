"""V5.5 stage 03: why is the proximity deviation unmeasured?

`trimesh.proximity.ProximityQuery.on_surface` returned a value my code could not unpack, and
the exception was being recorded inside a band entry rather than surfaced. This calls the
API directly and prints its true signature and return shape.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
RUNTIME = ROOT / "outcomes/v55/scenes/italian_flat/runtime"
PROPS = ROOT / "outcomes/v55/scenes/italian_flat/props"

print(f"trimesh {trimesh.__version__}")

# Pick whichever proxy parts exist for glass_a.
parts = sorted(PROPS.glob("glass_a_part*.obj"))
print(f"glass_a parts on disk: {len(parts)}")

vis = trimesh.load(str(RUNTIME / "Bicchiere_Cristallo_visual.obj"), process=True, force="mesh")
print(f"visual: {len(vis.vertices)} v / {len(vis.faces)} tri watertight={vis.is_watertight}")

if not parts:
    raise SystemExit("no parts to test")

tgt = trimesh.load(str(parts[0]), process=True, force="mesh")
print(f"part0: {len(tgt.vertices)} v / {len(tgt.faces)} tri")

print()
print("=== A. ProximityQuery.on_surface signature and return ===")
prox = trimesh.proximity.ProximityQuery(vis)
print(f"  on_surface doc: {(trimesh.proximity.ProximityQuery.on_surface.__doc__ or '')[:300]}")
pts = np.asarray(tgt.vertices, float)[:20]
try:
    res = prox.on_surface(pts)
    print(f"  returned type: {type(res)}")
    if isinstance(res, tuple):
        print(f"  tuple length: {len(res)}")
        for i, item in enumerate(res):
            try:
                arr = np.asarray(item)
                print(f"    [{i}] shape={arr.shape} dtype={arr.dtype} "
                      f"sample={arr.ravel()[:3]}")
            except Exception as exc:
                print(f"    [{i}] not array-like: {type(item)} ({exc})")
    else:
        arr = np.asarray(res)
        print(f"  shape={arr.shape} dtype={arr.dtype} sample={arr.ravel()[:5]}")
except Exception as exc:
    print(f"  on_surface RAISED: {type(exc).__name__}: {exc}")

print()
print("=== B. the signed_distance / nearest APIs ===")
for fn_name in ("signed_distance", "nearest", "nearest.on_surface"):
    try:
        if fn_name == "nearest.on_surface":
            prox2 = trimesh.proximity.ProximityQuery(vis)
            dist, idx = prox2.on_surface(pts)[:2]
            print(f"  {fn_name}: dist shape={np.asarray(dist).shape}")
        else:
            fn = getattr(trimesh.proximity, fn_name, None)
            if fn is None:
                print(f"  {fn_name}: absent")
                continue
            res = fn(vis, pts)
            print(f"  {fn_name}: {type(res)}")
            if isinstance(res, tuple):
                print(f"    tuple len={len(res)} shapes="
                      f"{[np.asarray(x).shape for x in res]}")
            else:
                print(f"    shape={np.asarray(res).shape}")
    except Exception as exc:
        print(f"  {fn_name}: RAISED {type(exc).__name__}: {exc}")

print()
print("=== C. simple independent check: vertex-to-nearest-vertex distance ===")
# A backend-free sanity metric, used to confirm the magnitude even if proximity fails.
tree = trimesh.util.bounds  # placeholder to avoid unused import lint
try:
    from scipy.spatial import cKDTree
    kd = cKDTree(np.asarray(vis.vertices, float))
    d, _ = kd.query(np.asarray(tgt.vertices, float))
    print(f"  cKDTree vertex-to-vertex: max={d.max()*1000:.4f} mm mean={d.mean()*1000:.4f} mm")
except Exception as exc:
    print(f"  cKDTree failed: {exc}")
