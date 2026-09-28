"""V5.5 stage 03 section 5: give the concave static tray a compound convex collider.

The problem, measured:

  * the tray `Vassoio` is an OPEN SHELL (84 boundary edges, euler 1) spanning z 0.500000 ..
    0.522260, with a floor at z = 0.510600 (59.7% of its sampled surface) and a rim reaching
    z = 0.522260 (15.6% of its surface);
  * handed to pybullet as a single GEOM_MESH, a 20 mm probe box rests with its bottom at
    z = 0.523247 -- the RIM height plus ~1 mm, i.e. ~12.6 mm above the real floor;
  * consequently every prop spawned at the measured floor height reports ~13.3 mm of initial
    penetration, and settles ~13 mm high.

03 section 5 requires every kerb a dynamic body could sweep into to HAVE collision, and the
tray's rim is exactly such a kerb. It also requires concave geometry to be represented
properly rather than filled. So the tray gets a compound of CONVEX parts via the same V-HACD
path already used for the props, and the resting height is then re-measured: props must come
to rest at the floor (z = 0.510600), not at the rim.

Deliverables: the tray's convex part files, a manifest with triangle counts and closure, and a
measured probe resting height for both the original shell and the compound, so the improvement
is a number rather than a claim.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pybullet as pb
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"
OUT = SCENES / "static_proxies"

DT = 1.0 / 480.0
FLOOR_Z = 0.510600
RIM_Z = 0.522260


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


def write_obj(path: Path, v, f):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as h:
        for p in v:
            h.write(f"v {p[0]:.9f} {p[1]:.9f} {p[2]:.9f}\n")
        for t in f:
            h.write(f"f {int(t[0])+1} {int(t[1])+1} {int(t[2])+1}\n")


def decompose(V, F, name: str, params: dict):
    info = {"method": None, "parts": 0, "dropped": 0, "error": None, "parameters": params}
    workdir = Path(tempfile.mkdtemp(prefix=f"vhacd_{name}_"))
    src, dst = workdir / "in.obj", workdir / "out.obj"
    write_obj(src, V, F)
    if not hasattr(pb, "vhacd"):
        info["method"] = "unavailable"
        return [], info
    try:
        pb.vhacd(str(src), str(dst), str(workdir / "log.txt"), **params)
    except Exception as exc:
        info["method"] = "failed"
        info["error"] = f"{type(exc).__name__}: {exc}"
        return [], info
    if not dst.is_file():
        info["method"] = "failed"
        info["error"] = "no output file"
        return [], info
    v, f = load_obj(dst)
    mesh = trimesh.Trimesh(vertices=v, faces=f, process=True)
    parts = []
    for comp in mesh.split(only_watertight=False):
        if len(comp.faces) < 4:
            info["dropped"] += 1
            continue
        if comp.is_watertight:
            parts.append((np.asarray(comp.vertices, float),
                          np.asarray(comp.faces, np.int64)))
        else:
            try:
                h = comp.convex_hull
                if len(h.faces):
                    parts.append((np.asarray(h.vertices, float),
                                  np.asarray(h.faces, np.int64)))
                else:
                    info["dropped"] += 1
            except Exception:
                info["dropped"] += 1
    info["method"] = "vhacd_convex_decomposition"
    info["parts"] = len(parts)
    return parts, info


def probe_rest(part_files: list[Path], label: str, out_manifest: dict) -> dict:
    """Drop a 20 mm box at several tray positions and report the resting bottom height."""
    cid = pb.connect(pb.DIRECT)
    try:
        pb.setGravity(0, 0, -9.81, physicsClientId=cid)
        pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                     physicsClientId=cid)
        statics = []
        if len(part_files) == 1:
            s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(part_files[0]),
                                        physicsClientId=cid)
            statics.append(pb.createMultiBody(0, s, basePosition=(0, 0, 0),
                                              physicsClientId=cid))
        else:
            for f in part_files:
                s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(f),
                                            physicsClientId=cid)
                statics.append(pb.createMultiBody(0, s, basePosition=(0, 0, 0),
                                                  physicsClientId=cid))
        Vs = [load_obj(f)[0] for f in part_files]
        V = np.vstack(Vs)
        lo, hi = V.min(axis=0), V.max(axis=0)
        half = 0.008
        bs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half] * 3,
                                     physicsClientId=cid)

        # Sample positions across the tray footprint, avoiding the extreme border where the
        # rim is, so the FLOOR height is what is measured.
        xs = np.linspace(lo[0] + 0.25 * (hi[0] - lo[0]), hi[0] - 0.25 * (hi[0] - lo[0]), 3)
        ys = np.linspace(lo[1] + 0.25 * (hi[1] - lo[1]), hi[1] - 0.25 * (hi[1] - lo[1]), 3)
        rests = []
        for x in xs:
            for y in ys:
                probe = pb.createMultiBody(0.05, bs,
                                           basePosition=(float(x), float(y), hi[2] + 0.03),
                                           physicsClientId=cid)
                for _ in range(int(2.0 / DT)):
                    pb.stepSimulation(physicsClientId=cid)
                p, _ = pb.getBasePositionAndOrientation(probe, physicsClientId=cid)
                n = sum(len(pb.getContactPoints(bodyA=probe, bodyB=b,
                                                physicsClientId=cid)) for b in statics)
                rests.append({"xy": [round(float(x), 6), round(float(y), 6)],
                              "bottom_z": round(float(p[2] - half), 6),
                              "contacts": n})
                pb.removeBody(probe, physicsClientId=cid)
        bottoms = [r["bottom_z"] for r in rests if r["contacts"] > 0]
        with_contact = [r for r in rests if r["contacts"] > 0]
        med = float(np.median(bottoms)) if bottoms else None
        print(f"  {label}: {len(with_contact)}/{len(rests)} probes found support; "
              f"bottom z median={('%.6f' % med) if med is not None else 'n/a'} "
              f"min={('%.6f' % min(bottoms)) if bottoms else 'n/a'} "
              f"max={('%.6f' % max(bottoms)) if bottoms else 'n/a'}")
        if med is not None:
            print(f"      vs FLOOR {FLOOR_Z:.6f}: {(med-FLOOR_Z)*1000:+.3f} mm   "
                  f"vs RIM {RIM_Z:.6f}: {(med-RIM_Z)*1000:+.3f} mm")
        return {"label": label, "probes": rests, "median_bottom_z": med,
                "min_bottom_z": min(bottoms) if bottoms else None,
                "max_bottom_z": max(bottoms) if bottoms else None,
                "probes_with_support": len(with_contact),
                "delta_vs_floor_m": (med - FLOOR_Z) if med is not None else None,
                "delta_vs_rim_m": (med - RIM_Z) if med is not None else None}
    finally:
        pb.disconnect(cid)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    tray = RUNTIME / "static_Vassoio.obj"
    V, F = load_obj(tray)
    print("=" * 76)
    print(f"=== tray: {len(V)} verts / {len(F)} tri  "
          f"z {V[:,2].min():.6f}..{V[:,2].max():.6f} ===")

    report: dict = {"source": str(tray), "floor_z": FLOOR_Z, "rim_z": RIM_Z}

    print("\n=== baseline: the original open shell as one GEOM_MESH ===")
    report["open_shell"] = probe_rest([tray], "open_shell", report)

    print("\n=== V-HACD convex decomposition of the tray ===")
    # Resolution rises across attempts. The residual error is a property of how finely the
    # shallow 22.26 mm dish is resolved: the floor is a thin, wide slab, so a coarse voxel grid
    # rounds its top surface upward. The measured progression is recorded rather than assumed.
    best = None
    for label, params in (
            ("coarse", {"resolution": 100000, "depth": 20, "concavity": 0.004,
                        "planeDownsampling": 4, "convexhullDownsampling": 4,
                        "alpha": 0.06, "beta": 0.06, "pca": 0, "mode": 0,
                        "convexhullApproximation": 1}),
            ("default", {"resolution": 200000, "depth": 20, "concavity": 0.002,
                         "planeDownsampling": 4, "convexhullDownsampling": 4,
                         "alpha": 0.04, "beta": 0.04, "pca": 0, "mode": 0,
                         "convexhullApproximation": 1}),
            ("fine", {"resolution": 800000, "depth": 24, "concavity": 0.0008,
                      "planeDownsampling": 4, "convexhullDownsampling": 4,
                      "alpha": 0.02, "beta": 0.02, "pca": 0, "mode": 0,
                      "convexhullApproximation": 1}),
            ("very_fine", {"resolution": 2000000, "depth": 28, "concavity": 0.0003,
                           "planeDownsampling": 2, "convexhullDownsampling": 2,
                           "alpha": 0.01, "beta": 0.01, "pca": 0, "mode": 0,
                           "convexhullApproximation": 1}),
    ):
        parts, info = decompose(V, F, "vassoio", params)
        print(f"  [{label}] {info['method']} parts={info['parts']} "
              f"dropped={info['dropped']} err={info.get('error')}")
        if not parts:
            continue
        d = OUT / f"vassoio_{label}"
        files = []
        for i, (pv, pf) in enumerate(parts):
            p = d / f"part{i:02d}.obj"
            write_obj(p, pv, pf)
            files.append(p)
        total_tris = sum(len(pf) for _, pf in parts)
        # Every part must be closed to be a valid convex collider.
        closed = all(trimesh.Trimesh(vertices=pv, faces=pf, process=True).is_watertight
                     for pv, pf in parts)
        print(f"      {len(files)} part files, {total_tris} tri, all closed={closed}")
        r = probe_rest(files, f"vhacd_{label}", report)
        r.update({"parts": len(files), "triangles": total_tris, "all_closed": closed,
                  "parameters": params, "files": [str(f) for f in files]})
        report[f"vhacd_{label}"] = r
        score = abs(r["delta_vs_floor_m"]) if r["delta_vs_floor_m"] is not None else 9e9
        if best is None or score < best[0]:
            best = (score, label, r)
        if r["delta_vs_floor_m"] is not None and abs(r["delta_vs_floor_m"]) < 0.001:
            print(f"      -> rests at the floor within 1 mm; enough")
            break

    if best:
        report["chosen"] = best[1]
        report["chosen_delta_vs_floor_m"] = best[2]["delta_vs_floor_m"]
        print(f"\n=== chosen tray collider: vhacd_{best[1]} "
              f"(delta vs floor {best[2]['delta_vs_floor_m']*1000:+.3f} mm) ===")

    p = SCENES / "tray_collider.json"
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"written: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
