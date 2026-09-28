"""V5.5 stage 03 section 4: diagnose the V-HACD failure on the open glasses.

V-HACD failed on both glasses with
  QhullError: QH6214 qhull input error: not enough points(3) to construct initial simplex
which is a Qhull error, not a V-HACD error: it comes from the convex-hull step applied to a
degenerate 3-point sliver that the decomposition emitted. That points at the IMPORTED MESH,
so this inspects the extracted OBJ itself.

The suspicion is that the exported glass mesh is not a clean closed solid: `wm.obj_export`
writes the visible surface, and an open tumbler's surface is a one-sided shell with a hole at
the mouth. V-HACD assumes a closed solid, so a holed shell can produce degenerate output.

This measures, rather than guesses, exactly what the exported glass mesh is.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path("/data/raw/huzijian/project1_database")
RUNTIME = ROOT / "outcomes/v55/scenes/italian_flat/runtime"

TARGETS = ["Bicchiere_Cristallo_visual.obj", "Bicchiere_Cristallo.001_visual.obj",
           "Bottiglia_Cristallo_visual.obj"]


def main() -> int:
    for fname in TARGETS:
        p = RUNTIME / fname
        print("=" * 74)
        print(f"=== {fname} ===")
        print("=" * 74)
        m = trimesh.load(str(p), process=True, force="mesh")
        print(f"  vertices={len(m.vertices)} faces={len(m.faces)}")
        print(f"  watertight={m.is_watertight}  winding_consistent={m.is_winding_consistent}")
        print(f"  euler_number={m.euler_number}")
        print(f"  volume={m.volume:.9e}")
        print(f"  body_count={m.body_count}  components={len(m.split(only_watertight=False))}")

        # Boundary edges: an open shell has edges used by exactly one face.
        edges = m.edges_sorted
        uniq, counts = np.unique(edges, axis=0, return_counts=True)
        boundary = int((counts == 1).sum())
        print(f"  boundary (open) edges: {boundary} of {len(uniq)}")
        print(f"  -> {'CLOSED solid' if boundary == 0 else 'OPEN shell: this is why V-HACD failed'}")

        # Does it enclose a hole at the mouth? Measure the opening.
        if boundary:
            bev = m.vertices[np.unique(uniq[counts == 1])]
            print(f"  open-boundary vertices: {len(bev)}")
            print(f"  boundary z range: {bev[:,2].min():.6f} .. {bev[:,2].max():.6f}")
            # Radius of the opening, which is what a hull would wrongly seal.
            centre = m.bounds.mean(axis=0)
            r = np.sqrt((bev[:,0]-centre[0])**2 + (bev[:,1]-centre[1])**2)
            print(f"  boundary radius: min={r.min():.6f} max={r.max():.6f} "
                  f"(a hull would seal this {2*r.max()*1000:.1f} mm opening)")
            print(f"  boundary normal_z range: "
                  f"{'upward' if bev[:,2].max() > m.bounds[1][2] - 0.01 else 'not at top'}")

        # Can trimesh repair it?  This decides whether a closed proxy is achievable at all.
        try:
            filled = m.copy()
            filled.fill_holes()
            print(f"  after fill_holes: watertight={filled.is_watertight} "
                  f"faces={len(filled.faces)}")
        except Exception as exc:
            print(f"  fill_holes failed: {type(exc).__name__}: {exc}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
