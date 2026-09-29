"""Check where PyBullet will put each collision mesh's centre of mass, and whether that is right.

WHY THIS EXISTS
---------------
A parallel investigation of the box assets found, and proved, that this PyBullet build places a
`GEOM_MESH` body's centre of mass at the OBJ FILE's own origin. The demonstration was decisive: an
upright proxy whose base sat at z = 0 in the file had its COM on the floor, so gravity restored it
upright however far it was tipped -- a box released 70 degrees past its balance point sprang back to
standing -- and the same hull with an explicit inertial-frame offset toppled correctly.

That matters here because `MultibodySolver` builds every body as
`createMultiBody(mass, createCollisionShape(GEOM_MESH, fileName=...), basePosition=...)` with no
`baseInertialFramePosition`, so the COM is wherever the OBJ's origin happens to be.

The pipeline's own convention is that a collision proxy is RECENTRED so its AABB centre is the mesh
origin, and `position_m` is that centre (V5.6 section 3.1 records `glass_b_collision.obj` spanning
z in [-0.052197, +0.052197]). Under that convention the COM lands at the geometric centre, which is
the right place. But that is a convention that has to HOLD for every proxy, and a single proxy
exported in its authored coordinates rather than recentred would put its COM somewhere else and give
wrong tipping behaviour with no error message.

So this measures the offset for every collision mesh a run uses and reports it, rather than assuming
the convention was followed. A proxy whose AABB centre is not near the file origin is flagged, and
what that does to the COM is stated in the object's own terms.

Read-only. Run with the control interpreter (no bpy):

    python tools\\v56\\check_com_origin.py --run <run_dir> [--tol 0.005]
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def obj_aabb(path: Path):
    mn = [1e18] * 3
    mx = [-1e18] * 3
    n = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith("v "):
                continue
            p = line.split()
            if len(p) < 4:
                continue
            try:
                v = [float(p[1]), float(p[2]), float(p[3])]
            except ValueError:
                continue
            for i in range(3):
                mn[i] = min(mn[i], v[i])
                mx[i] = max(mx[i], v[i])
            n += 1
    if n == 0:
        return None
    return mn, mx, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--extra", default="", help="comma-separated extra OBJ paths to check")
    ap.add_argument("--tol", type=float, default=0.005,
                    help="how far the AABB centre may sit from the file origin, in metres")
    A = ap.parse_args()

    run = Path(A.run)
    cands = sorted(run.glob("*_collision.obj")) + sorted(run.glob("**/*_collision.obj"))
    if A.extra:
        cands += [Path(p) for p in A.extra.split(",") if p.strip()]
    seen = set()
    uniq = []
    for c in cands:
        if c.resolve() not in seen and c.is_file():
            seen.add(c.resolve())
            uniq.append(c)

    if not uniq:
        print(f"no collision meshes found under {run}; nothing to check")
        return 1

    print("=" * 100)
    print("collision mesh centre-of-mass placement check")
    print(f"  PyBullet puts a GEOM_MESH body's COM at the OBJ file origin, and this solver passes no")
    print(f"  baseInertialFramePosition, so the file origin IS the COM. Tolerance {A.tol * 1000:.1f} mm.")
    print()

    results = []
    flagged = 0
    for p in uniq:
        a = obj_aabb(p)
        if a is None:
            continue
        mn, mx, nv = a
        centre = [(mn[i] + mx[i]) / 2.0 for i in range(3)]
        dist = sum(c * c for c in centre) ** 0.5
        dims = [mx[i] - mn[i] for i in range(3)]
        ok = dist <= A.tol
        if not ok:
            flagged += 1
        # Where the lowest point of the mesh sits relative to the COM, which is the quantity that
        # decides tipping: if the COM is at the base, the body cannot topple at all.
        com_height_above_base = centre[2] - mn[2]
        results.append({
            "file": str(p), "name": p.name, "vertices": nv,
            "local_aabb_min": mn, "local_aabb_max": mx, "dims_m": dims,
            "aabb_centre_offset_m": centre, "offset_from_origin_m": dist,
            "com_height_above_lowest_point_m": com_height_above_base,
            "tipping_possible": com_height_above_base > 1e-4,
            "pass": ok,
        })
        print(f"  {'PASS' if ok else 'FLAG'}  {p.name:44s} dims "
              f"{[round(d, 5) for d in dims]}")
        print(f"          AABB centre offset from origin {[round(c, 6) for c in centre]} m "
              f"(|offset| {dist * 1000:.3f} mm)")
        print(f"          COM sits {com_height_above_base * 1000:.3f} mm above the mesh's lowest "
              f"point -> {'can topple' if com_height_above_base > 1e-4 else 'CANNOT TOPPLE'}")

    print()
    if flagged == 0:
        print(f"  all {len(results)} collision meshes are recentred on their own origin, so the COM")
        print(f"  lands at the geometric centre. The pipeline convention holds for this run.")
    else:
        print(f"  {flagged} of {len(results)} collision meshes are NOT recentred on their origin.")
        print(f"  For each, the COM will sit at the file origin, which is not the geometric centre;")
        print(f"  the offset above is how far wrong it is. This must be corrected by recentring the")
        print(f"  proxy (or by passing baseInertialFramePosition) before any result from this run is")
        print(f"  trusted for tipping.")

    out = run / "com_origin_check.json"
    out.write_text(json.dumps({
        "tolerance_m": A.tol,
        "method": ("reads each collision OBJ's own vertex AABB; PyBullet places a GEOM_MESH COM at "
                   "the file origin and this solver passes no baseInertialFramePosition, so a "
                   "non-zero AABB centre means a misplaced COM"),
        "meshes": results, "flagged": flagged, "all_pass": flagged == 0,
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {out}")
    return 0 if flagged == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
