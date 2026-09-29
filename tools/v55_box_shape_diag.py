"""Diagnose why the flat-face measurement returned near-zero for every asset.

`v55_box_shape_check.py` reported a flat-bottom area fraction of 0.007-0.058 for every asset,
including one whose name says it is a cube. A cube cannot have a 5% flat bottom, so the measurement
is wrong and this finds out why before any conclusion is drawn from it.

Two candidate explanations, and this distinguishes them:

  (a) **Orientation.** GSO assets are scans of real objects, so each mesh may be stored in an
      arbitrary pose, not with Z up. Measuring "the bottom face along the tallest axis" would then
      be measuring a slanted surface. The fix is to measure flatness along EVERY axis direction and
      also along the axes of the object's own principal frame, and to read the asset's recorded
      alignment from `data.json` / the URDF.
  (b) **Sampling.** Counting a whole triangle as "on the plane" only when its three vertices are all
      within a tolerance is fragile for meshes whose extreme face is split into thin slivers, or
      whose extreme is a single vertex rather than a face.

It reports, for each asset, the flatness along all six axis directions and the recorded orientation
metadata, so the actual cause is visible rather than assumed.

Read-only.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"

ASSETS = [
    "Room_Essentials_Fabric_Cube_Lavender",
    "Star_Wars_Rogue_Squadron_Nintendo_64",
    "Hasbro_Cranium_Performance_and_Acting_Game",
    "Android_Lego",
]


def read_obj(path: Path):
    verts, tris = [], []
    with path.open("r", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                verts.append((float(p[1]), float(p[2]), float(p[3])))
            elif line.startswith("f "):
                idx = []
                for tok in line.split()[1:]:
                    s = tok.split("/")[0]
                    if s.lstrip("-").isdigit():
                        i = int(s)
                        idx.append(i - 1 if i > 0 else len(verts) + i)
                for k in range(1, len(idx) - 1):
                    tris.append((idx[0], idx[k], idx[k + 1]))
    return verts, tris


def tri_area(p0, p1, p2):
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
    cx = uy * vz - uz * vy
    cy = uz * vx - ux * vz
    cz = ux * vy - uy * vx
    return 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)


def flatness_all_axes(verts, tris):
    """Area fraction within tol of each of the six bounding-box faces."""
    out = {}
    for axis, nm in enumerate("xyz"):
        lo = min(v[axis] for v in verts)
        hi = max(v[axis] for v in verts)
        span = hi - lo
        tol = 0.02 * span
        total = 0.0
        lo_a = 0.0
        hi_a = 0.0
        for a, b, c in tris:
            try:
                p0, p1, p2 = verts[a], verts[b], verts[c]
            except IndexError:
                continue
            ar = tri_area(p0, p1, p2)
            total += ar
            dlo = max(abs(p0[axis] - lo), abs(p1[axis] - lo), abs(p2[axis] - lo))
            dhi = max(abs(p0[axis] - hi), abs(p1[axis] - hi), abs(p2[axis] - hi))
            if dlo <= tol:
                lo_a += ar
            if dhi <= tol:
                hi_a += ar
        out[f"{nm}_lo"] = round(lo_a / total, 4) if total else None
        out[f"{nm}_hi"] = round(hi_a / total, 4) if total else None
    return out


def flatness_max_not_sum(verts, tris):
    """Same, but counting a triangle when its vertices are within tol using MAX distance.

    The earlier version averaged the three distances, which for a large triangle touching the plane
    at one corner and rising away still averages below tol and gets counted, inflating the number.
    Using max distance is the conservative choice.
    """
    out = {}
    for axis, nm in enumerate("xyz"):
        lo = min(v[axis] for v in verts)
        hi = max(v[axis] for v in verts)
        span = hi - lo
        tol = 0.02 * span
        total = lo_a = hi_a = 0.0
        for a, b, c in tris:
            try:
                p0, p1, p2 = verts[a], verts[b], verts[c]
            except IndexError:
                continue
            ar = tri_area(p0, p1, p2)
            total += ar
            if max(abs(p0[axis] - lo), abs(p1[axis] - lo), abs(p2[axis] - lo)) <= tol:
                lo_a += ar
            if max(abs(p0[axis] - hi), abs(p1[axis] - hi), abs(p2[axis] - hi)) <= tol:
                hi_a += ar
        out[f"{nm}_lo_max"] = round(lo_a / total, 4) if total else None
        out[f"{nm}_hi_max"] = round(hi_a / total, 4) if total else None
    return out


report = {}
for name in ASSETS:
    d = GSO / name
    coll, vis = d / "collision_geometry.obj", d / "visual_geometry.obj"
    entry = {"has_collision": coll.is_file()}
    dj = d / "data.json"
    if dj.is_file():
        try:
            meta = json.loads(dj.read_text(encoding="utf-8", errors="replace"))
            # Only orientation-relevant keys; the full file is large.
            keep = {k: v for k, v in meta.items()
                    if any(s in k.lower() for s in ("rot", "quat", "axis", "up", "scale",
                                                    "align", "pose", "trans", "dim", "size", "bbox"))}
            entry["data_json_orientation_keys"] = keep
            entry["data_json_keys"] = sorted(meta.keys())
        except Exception as e:
            entry["data_json_error"] = str(e)
    urdf = d / "object.urdf"
    if urdf.is_file():
        entry["urdf_head"] = urdf.read_text(encoding="utf-8", errors="replace")[:700]
    # `.obj`/`.mtl` companions that might record an axis conversion
    entry["files"] = sorted(p.name for p in d.iterdir())

    for label, src in (("visual", vis), ("collision", coll)):
        if not src.is_file():
            continue
        verts, tris = read_obj(src)
        entry[f"{label}_vertices"] = len(verts)
        entry[f"{label}_triangles"] = len(tris)
        if not verts:
            continue
        dx = max(v[0] for v in verts) - min(v[0] for v in verts)
        dy = max(v[1] for v in verts) - min(v[1] for v in verts)
        dz = max(v[2] for v in verts) - min(v[2] for v in verts)
        entry[f"{label}_extents"] = [round(dx, 5), round(dy, 5), round(dz, 5)]
        entry[f"{label}_flat_avg"] = flatness_all_axes(verts, tris)
        entry[f"{label}_flat_max"] = flatness_max_not_sum(verts, tris)
    report[name] = entry

print("=" * 110)
for name, e in report.items():
    print(f"\n### {name}")
    print(f"  files: {e['files']}")
    print(f"  collision proxy: {e['has_collision']}")
    if e.get("data_json_keys"):
        print(f"  data.json keys: {e['data_json_keys']}")
    if e.get("data_json_orientation_keys"):
        print(f"  orientation-ish keys: {json.dumps(e['data_json_orientation_keys'])[:400]}")
    for label in ("visual", "collision"):
        if f"{label}_extents" not in e:
            continue
        print(f"  {label}: {e[f'{label}_vertices']} v / {e[f'{label}_triangles']} t  "
              f"extents {e[f'{label}_extents']}")
        print(f"    flatness (avg-dist method, the earlier one):")
        for k, v in e[f"{label}_flat_avg"].items():
            if v and v > 0.3:
                print(f"      {k:10s} {v}")
        print(f"    flatness (max-dist method, conservative):")
        for k, v in e[f"{label}_flat_max"].items():
            if v and v > 0.3:
                print(f"      {k:10s} {v}")
    if e.get("urdf_head"):
        print(f"  urdf: {e['urdf_head'][:300]}")

(ROOT / "outcomes/v55/stage08/box_shape_diagnosis.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8")
print(f"\nwritten: {ROOT / 'outcomes/v55/stage08/box_shape_diagnosis.json'}")
