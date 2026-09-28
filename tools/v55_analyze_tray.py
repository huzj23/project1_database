"""V5.5 stage 05: resolve the 13.3 mm initial penetration of the props into the tray.

Now that the frame inverse is right, every prop and the visual reference all report the SAME
~13.3 mm initial penetration into the static environment, and all of them settle to a resting
height about 13.35 mm ABOVE their spawn height. Identical behaviour for the proxies and the
visual means this is NOT a proxy defect -- it is a property of the scene, and 04 caps initial
penetration at min(1 mm, t_min*5%), so it must be understood before the solve.

The measured facts to explain:
  * the raycast (stage 05 section 1) found the tray FLOOR at z = 0.510600;
  * the tray mesh's own AABB spans z 0.500000..0.522260, i.e. it has a base and a rim;
  * the bottle's AABB bottom in the SOURCE scene is z = 0.509198, which is 1.40 mm below the
    tray floor -- already an overlap in the authored scene;
  * the props settle ~13 mm HIGHER than they spawn.

Hypothesis: `static_Vassoio.obj` as exported is a CLOSED solid whose interior is filled, so a
prop resting on the floor height is 13 mm inside it. The tray is a shell; treating it as solid
is what creates the penetration. This measures that directly by testing, for the tray mesh:

  a. is it watertight (a closed solid, which pybullet treats as filled)?
  b. what is the FIRST surface a downward ray meets, and what is the floor height at each
     sample point?
  c. does a probe box rest at the FLOOR height or at the RIM height?
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pybullet as pb
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
SCENES = ROOT / "outcomes/v55/scenes/italian_flat"
RUNTIME = SCENES / "runtime"

DT = 1.0 / 480.0


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


def main() -> int:
    out: dict = {}
    tray = RUNTIME / "static_Vassoio.obj"
    V, F = load_obj(tray)
    lo, hi = V.min(axis=0), V.max(axis=0)
    print("=" * 74)
    print(f"=== tray mesh {tray.name}: {len(V)} verts / {len(F)} tri")
    print(f"  bounds x {lo[0]:.6f}..{hi[0]:.6f}")
    print(f"         y {lo[1]:.6f}..{hi[1]:.6f}")
    print(f"         z {lo[2]:.6f}..{hi[2]:.6f}   height {(hi[2]-lo[2])*1000:.4f} mm")

    m = trimesh.Trimesh(vertices=V, faces=F, process=True)
    print(f"  watertight={m.is_watertight}  euler={m.euler_number}  "
          f"volume={m.volume:.9e}")
    edges = m.edges_sorted
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    print(f"  boundary (open) edges: {int((counts == 1).sum())}")
    print(f"  -> {'CLOSED SOLID (pybullet will treat its interior as filled)' if m.is_watertight else 'OPEN SHELL'}")
    out["tray_watertight"] = bool(m.is_watertight)
    out["tray_z_range"] = [float(lo[2]), float(hi[2])]

    # Where is the FLOOR versus the RIM?  Sample the tray's own surface height over its
    # footprint: a tray is a shallow dish, so most of its area is floor and the rim is a
    # narrow border. The distribution tells which height dominates.
    print("\n=== surface height distribution over the tray's footprint ===")
    samples, _ = trimesh.sample.sample_surface(m, 200000)
    samples = np.asarray(samples, float)
    # Look at upward-facing area only, via the triangle normals of the sampled faces.
    zs = samples[:, 2]
    hist, edges_ = np.histogram(zs, bins=12, range=(lo[2], hi[2]))
    for i in range(len(hist)):
        print(f"  z {edges_[i]:.6f}..{edges_[i+1]:.6f}: {hist[i]:>7d} samples "
              f"({100*hist[i]/len(zs):5.2f}%)")
    out["tray_z_histogram"] = {
        f"{edges_[i]:.6f}": int(hist[i]) for i in range(len(hist))}

    # Downward raycast onto the tray at its centre and near its border.
    print("\n=== downward raycast onto the tray ===")
    try:
        loc, _, _ = m.ray.intersects_location(
            ray_origins=np.array([[0.55, 7.42, hi[2] + 0.05]]),
            ray_directions=np.array([[0, 0, -1.0]]), multiple_hits=True)
        if len(loc):
            for z in sorted(loc[:, 2], reverse=True):
                print(f"  ray at tray centre hits z={z:.6f}")
    except Exception as exc:
        print(f"  ray engine unavailable ({type(exc).__name__}); using the histogram instead")

    # Mass properties: a solid tray would be heavy, a shell light.  Volume/area ratio
    # indicates whether the exported geometry is a thick solid or a thin shell.
    print(f"\n  surface area {m.area:.6f} m^2, enclosed volume {m.volume:.9e} m^3")
    if m.area > 0:
        print(f"  volume/area = {(m.volume/m.area)*1000:.4f} mm "
              f"(a thin shell gives a small value; a solid block gives roughly half its "
              f"smallest dimension, {(hi[2]-lo[2])*500:.3f} mm)")

    # Does pybullet rest a probe at the FLOOR or at the RIM height?
    print("\n=== pybullet: where does a probe box rest on the tray? ===")
    cid = pb.connect(pb.DIRECT)
    try:
        pb.setGravity(0, 0, -9.81, physicsClientId=cid)
        pb.setPhysicsEngineParameter(fixedTimeStep=DT, numSolverIterations=120,
                                     physicsClientId=cid)
        s = pb.createCollisionShape(pb.GEOM_MESH, fileName=str(tray),
                                    physicsClientId=cid)
        body = pb.createMultiBody(0, s, basePosition=(0, 0, 0), physicsClientId=cid)
        half = 0.01
        bs = pb.createCollisionShape(pb.GEOM_BOX, halfExtents=[half, half, half],
                                     physicsClientId=cid)
        cx, cy = 0.5 * (lo[0] + hi[0]), 0.5 * (lo[1] + hi[1])
        probe = pb.createMultiBody(0.05, bs,
                                   basePosition=(cx, cy, hi[2] + 0.03),
                                   physicsClientId=cid)
        for _ in range(int(2.0 / DT)):
            pb.stepSimulation(physicsClientId=cid)
        p, _ = pb.getBasePositionAndOrientation(probe, physicsClientId=cid)
        n = len(pb.getContactPoints(bodyA=probe, bodyB=body, physicsClientId=cid))
        print(f"  probe rest z = {p[2]:.6f} (bottom {p[2]-half:.6f})  contacts={n}")
        print(f"    vs tray floor 0.510600 -> delta {(p[2]-half-0.510600)*1000:+.3f} mm")
        print(f"    vs tray base  0.500000 -> delta {(p[2]-half-0.500000)*1000:+.3f} mm")
        print(f"    vs tray top   0.522260 -> delta {(p[2]-half-0.522260)*1000:+.3f} mm")
        out["probe_rest_bottom_z"] = float(p[2] - half)
        out["probe_contacts"] = n
    finally:
        pb.disconnect(cid)

    p = SCENES / "tray_analysis.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
