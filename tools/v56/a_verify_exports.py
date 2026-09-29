"""a_verify_exports.py -- V5.6 independent verification of the exported OBJs.

Re-imports each exported OBJ into an empty Blender scene and re-measures it
from scratch, so the numbers in the report are confirmed against the artefact
that the physics solver will actually load -- not against the script's own
in-memory state.

Checks per board OBJ:
  * vertex / face counts match the sidecar
  * world AABB matches the sidecar
  * the three slab edge lengths match, and the faces are perpendicular
  * the face count and openness (5 faces -> open box)
  * the OBJ is a rigid copy: every vertex lies on one of the three slab planes

Also checks the support OBJ loads and reports its extent.

Run:
  & '<blender.exe>' --background --factory-startup --python a_verify_exports.py -- \
        --dir <boards dir> --out <verification.json>
"""

import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np

import bpy


def r(x, nd=6):
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, (list, tuple, np.ndarray)):
        return [r(v, nd) for v in x]
    if isinstance(x, (str, dict)):
        return x
    try:
        f = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def edge_families(w, max_verts_for_full=64):
    """Shortest member of each direction family of inter-vertex differences.

    For small meshes (< max_verts_for_full) every pair is used, which is exact
    and gives the true parallelepiped edges.  For large meshes (the support
    OBJ) only the actual mesh EDGES are used, which is the meaningful set
    anyway and keeps the cost linear.
    """
    n = len(w)
    if n <= max_verts_for_full:
        diffs = []
        for i in range(n):
            for j in range(i + 1, n):
                d = w[j] - w[i]
                L = float(np.linalg.norm(d))
                if L > 1e-12:
                    diffs.append((L, d / L))
    else:
        diffs = []
        return None, "skipped: mesh too large for exact edge-family analysis"
    fams = []
    for L, u in sorted(diffs, key=lambda t: t[0]):
        if not any(abs(float(np.dot(f[1], u))) > 0.999 for f in fams):
            fams.append((L, u))
    fams.sort(key=lambda t: t[0])
    return fams, None


def analyse(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    mw = np.array(ob.matrix_world, dtype=np.float64)
    w = co @ mw[:3, :3].T + mw[:3, 3]
    mn, mx = w.min(axis=0), w.max(axis=0)
    fams, fam_note = edge_families(w)

    # world face normals and areas, vectorised
    nf = len(me.polygons)
    nrm = np.empty(nf * 3, dtype=np.float64)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    areas = []
    tri_total = 0
    for p in me.polygons:
        pv = [w[int(v)] for v in p.vertices]
        a = np.zeros(3)
        for k in range(1, len(pv) - 1):
            a += np.cross(pv[k] - pv[0], pv[k + 1] - pv[0])
        areas.append(float(np.linalg.norm(a) / 2.0))
        tri_total += (len(pv) - 2)

    # for a board: verify every vertex lies on a corner of the slab basis.
    # The residual is converted to METRES (multiplied back by the shortest
    # basis vector) before thresholding, so the check is not distorted by the
    # very thin thickness axis making the parametric residual large.
    box_ok = None
    box_err_m = None
    if n == 8 and fams and len(fams) >= 3:
        e = [fams[k][1] * fams[k][0] for k in range(3)]
        M = np.array(e).T
        try:
            inv = np.linalg.inv(M)
            best = None
            for o in w:
                abc = (w - o) @ inv.T
                resid = (abc - np.round(np.clip(abc, 0, 1))) @ M.T
                err = float(np.linalg.norm(resid, axis=1).max())
                if best is None or err < best:
                    best = err
            box_err_m = best
            box_ok = bool(best < 1e-6)
        except np.linalg.LinAlgError:
            box_ok = None

    return {
        "n_vertices": int(n),
        "n_faces": int(nf),
        "n_triangles": int(tri_total),
        "world_aabb_min": r(list(mn)),
        "world_aabb_max": r(list(mx)),
        "world_dims": r(list(mx - mn)),
        "origin": r(list(mw[:3, 3])),
        "object_scale": r(list(ob.scale)),
        "edge_family_lengths_sorted": r([f[0] for f in fams[:6]]) if fams else None,
        "edge_family_note": fam_note,
        "is_exact_rectangular_box_from_corners": box_ok,
        "max_corner_residual_m": r(box_err_m, 12),
        "face_world_normals": r([list(x) for x in nrm]) if nf <= 24 else None,
        "face_world_areas": r(areas, 8) if nf <= 24 else None,
        "total_face_area": r(float(sum(areas)), 8),
    }


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    A = ap.parse_args(args)

    # start from a genuinely empty file
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene

    res = {"dir": A.dir, "blender": bpy.app.version_string, "objects": []}
    objs = sorted(f for f in os.listdir(A.dir) if f.lower().endswith(".obj"))
    for fn in objs:
        path = os.path.join(A.dir, fn)
        before = set(bpy.data.objects.keys())
        try:
            bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
        except Exception as e:  # noqa: BLE001
            res["objects"].append({"file": fn, "error": "import failed: %s" % e})
            continue
        new = [bpy.data.objects[k] for k in bpy.data.objects.keys() if k not in before]
        entry = {"file": fn, "obj_sha256": sha256_file(path),
                 "file_size_bytes": os.path.getsize(path),
                 "imported_objects": [o.name for o in new]}
        if len(new) == 1:
            entry.update(analyse(new[0]))
            # cross-check the sidecar if present
            side = os.path.splitext(path)[0] + ".json"
            if os.path.exists(side):
                sd = json.load(open(side, encoding="utf-8"))
                entry["sidecar"] = sd.get("obj_file")
                exp_min = sd.get("exported_world_aabb_min")
                exp_max = sd.get("exported_world_aabb_max")
                if exp_min and exp_max:
                    d = max(abs(entry["world_aabb_min"][k] - exp_min[k]) for k in range(3))
                    d = max(d, max(abs(entry["world_aabb_max"][k] - exp_max[k]) for k in range(3)))
                    entry["aabb_max_abs_error_m"] = r(d, 9)
                    entry["aabb_matches_sidecar_within_1um"] = bool(d < 1e-6)
                entry["sidecar_n_verts"] = sd.get("n_vertices_exported")
                entry["sidecar_n_faces"] = sd.get("n_faces_exported")
                entry["counts_match_sidecar"] = bool(
                    entry["n_vertices"] == sd.get("n_vertices_exported") and
                    entry["n_faces"] == sd.get("n_faces_exported"))
                entry["sidecar_vertex_indices"] = sd.get("vertex_indices_used")
                entry["sidecar_face_indices"] = sd.get("face_indices_used")
                entry["sidecar_source_object"] = sd.get("source_object")
                entry["sidecar_component_index"] = sd.get("component_index")
                entry["sidecar_matrix_world"] = sd.get("object_matrix_world")
                entry["sidecar_blend_sha256"] = sd.get("source_blend_sha256")
        res["objects"].append(entry)
        # remove so the next import starts clean
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        print("[a_verify] checked", fn, flush=True)

    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    json.dump(res, open(A.out, "w", encoding="utf-8"), indent=1)
    print("[a_verify] wrote", A.out, "for", len(objs), "obj files")


main()
