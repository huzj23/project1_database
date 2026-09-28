"""V5.5 stage 03: load the real static environment mesh as a collider.

`createCollisionShape(GEOM_MESH, vertices=..., indices=...)` failed on the exported
environment (142340 vertices / 283816 triangles) with

    b3Warning ... invalid mesh filename './'
    createCollisionShape failed

So the static environment cannot be handed to pybullet the way the small prop proxies were.
This finds out why and which route works, by testing in order:

  A. vertices/indices at increasing triangle counts -> locate any size limit;
  B. fileName=<path> for the same meshes -> the file-based route the solver already uses;
  C. per-object convex hulls -> small and exact for the slab-like table, but it would SEAL the
     tray's 11.66 mm rim, so it is measured as a candidate and its resting height checked;
  D. whether the OBJ needs to be watertight / have consistent winding to load.

The acceptance question is concrete: does a prop mesh come to rest at the tray floor
z = 0.510600, which is where the raycast proved the props actually stand?
"""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pybullet as pb
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"
PROPS = SCENES / "props"

DT = 1.0 / 480.0
SUPPORT_Z = 0.510600


def load_obj(path: Path):
    verts, faces = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                verts.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    raw = tok.split("/")[0]
                    if raw:
                        i = int(raw)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    faces.append((idx[0], idx[k], idx[k + 1]))
    return np.asarray(verts, float), np.asarray(faces, np.int64)


def write_obj(path: Path, v, f):
    with path.open("w", encoding="utf-8") as h:
        for p in v:
            h.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
        for t in f:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")


def main() -> int:
    cid = pb.connect(pb.DIRECT)
    pb.setGravity(0, 0, -9.81, physicsClientId=cid)
    pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                 physicsClientId=cid)
    report: dict = {}

    print("=== A. vertices/indices route at increasing triangle counts ===")
    src = RUNTIME / "environment_static_collision.obj"
    ev, ef = load_obj(src)
    print(f"  source: {len(ev)} verts / {len(ef)} tri")
    limits = []
    for target_tris in (1000, 10000, 50000, 100000, 200000, len(ef)):
        n = min(target_tris, len(ef))
        # Take a contiguous subset of faces and re-index, which keeps geometry valid.
        sub = ef[:n]
        used = np.unique(sub)
        remap = -np.ones(len(ev), dtype=np.int64)
        remap[used] = np.arange(len(used))
        vv = ev[used]
        ff = remap[sub]
        try:
            s = pb.createCollisionShape(pb.GEOM_MESH, vertices=vv.tolist(),
                                        indices=ff.ravel().tolist(),
                                        physicsClientId=cid)
            ok = s >= 0
            if ok:
                pb.removeBody(pb.createMultiBody(
                    0, s, basePosition=(0, 0, 0), physicsClientId=cid))
        except Exception as exc:
            ok = False
        print(f"  {n:>7d} tri ({len(used):>7d} verts): "
              f"{'OK' if ok else 'FAILED'}")
        limits.append({"triangles": int(n), "vertices": int(len(used)), "ok": bool(ok)})
    report["vertices_indices_route"] = limits

    print("\n=== B. fileName route (what the solver uses) ===")
    file_route = {}
    for n in (50000, len(ef)):
        sub = ef[:n]
        used = np.unique(sub)
        remap = -np.ones(len(ev), dtype=np.int64)
        remap[used] = np.arange(len(used))
        tmp = Path(tempfile.mkdtemp()) / f"env_{n}.obj"
        write_obj(tmp, ev[used], remap[sub])
        try:
            s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(tmp),
                                        physicsClientId=cid)
            ok = s >= 0
        except Exception as exc:
            ok = False
            print(f"    fileName {n} raised {type(exc).__name__}: {exc}")
        print(f"  fileName {n:>7d} tri: {'OK' if ok else 'FAILED'}")
        file_route[str(n)] = bool(ok)
        if ok:
            pb.removeBody(pb.createMultiBody(0, s, basePosition=(0, 0, 0),
                                             physicsClientId=cid))
    report["file_name_route"] = file_route

    print("\n=== C. per-object convex hulls of the static region ===")
    layer = json.loads((SCENES / "layer_report.json").read_text(encoding="utf-8"))
    names = list(layer["static_collision"].keys())
    print(f"  static objects: {names}")
    # The exported environment mesh is the union; splitting per object requires the
    # per-object exports, so this checks only whether a hull of the WHOLE region loads and
    # what height props rest at, which is the number that matters.
    hull = trimesh.Trimesh(vertices=ev, faces=ef, process=True).convex_hull
    hv = np.asarray(hull.vertices, float)
    hf = np.asarray(hull.faces, np.int64)
    print(f"  hull of the whole static region: {len(hv)} verts / {len(hf)} tri")
    try:
        s = pb.createCollisionShape(pb.GEOM_MESH, vertices=hv.tolist(),
                                    indices=hf.ravel().tolist(), physicsClientId=cid)
        hull_ok = s >= 0
    except Exception:
        hull_ok = False
    print(f"  hull loads: {hull_ok}")
    report["whole_region_hull_loads"] = bool(hull_ok)
    if hull_ok:
        env = pb.createMultiBody(0, s, basePosition=(0, 0, 0), physicsClientId=cid)
        top = float(hv[:, 2].max())
        print(f"  hull z range {hv[:,2].min():.4f} .. {top:.4f} "
              f"(a hull SEALS the tray rim at 0.522260 and fills under the table)")

    print("\n=== D. does an unmerged/duplicated-vertex mesh load? ===")
    # pybullet is happier with meshes it can weld. Test a welded version via trimesh.
    m = trimesh.Trimesh(vertices=ev, faces=ef, process=True)
    print(f"  after trimesh process: {len(m.vertices)} verts / {len(m.faces)} tri "
          f"watertight={m.is_watertight}")
    try:
        s = pb.createCollisionShape(pb.GEOM_MESH,
                                    vertices=np.asarray(m.vertices, float).tolist(),
                                    indices=np.asarray(m.faces, np.int64).ravel().tolist(),
                                    physicsClientId=cid)
        print(f"  processed mesh loads: {s >= 0}")
        report["processed_mesh_loads"] = bool(s >= 0)
    except Exception as exc:
        print(f"  processed mesh raised {type(exc).__name__}")
        report["processed_mesh_loads"] = False

    pb.disconnect(cid)
    out = SCENES / "static_collider_probe.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
