"""a_export_boards.py -- V5.6 export the chosen board and its alternates.

Exports, into a target directory, preserving WORLD coordinates:

  board_<rank>_<object>_c<idx>.obj   the isolated board component, one per
                                     ranked candidate, plus
  support_wall_ground.obj            a small "support" OBJ containing just the
                                     wall and ground geometry immediately
                                     around the chosen board, so the physics
                                     solver has the leaning surface and the
                                     floor.

Every export writes a sibling .json sidecar recording: source object name,
component index, the exact vertex and face indices used, the source .blend
SHA-256, the object's world matrix, the per-vertex world coordinates actually
written, and the computed AABB / dimensions / volume / mass estimate.

The scene is never modified on disk (no save).  Nothing is deleted.

Run:
  & '<blender.exe>' --background --factory-startup --python a_export_boards.py -- \
        --blend <scene.blend> --outdir <dir> --choice <object>:<component_index> \
        [--choice <object>:<component_index> ...] \
        [--support-objects a,b,c] [--support-pad 0.6]
"""

import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np

import bpy

DENSITIES = {"pine_low": 400.0, "softwood_mid": 500.0, "hardwood_high": 700.0}
DEFAULT_SUPPORT = [
    "apartment_walls",
    "base_tripple_01.003",
    "Floor_main",
    "stones",
]


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
            blk = fh.read(chunk)
            if not blk:
                break
            h.update(blk)
    return h.hexdigest()


def components_of(me, nv):
    parent = list(range(nv))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    comp = [find(i) for i in range(nv)]
    order = []
    for i in range(nv):
        if comp[i] not in order:
            order.append(comp[i])
    return comp, order


def world_coords(ob):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    mw = np.array(ob.matrix_world, dtype=np.float64)
    return co @ mw[:3, :3].T + mw[:3, 3], co, mw


def write_obj(path, verts_world, faces_local_idx, header_lines):
    """Write a minimal OBJ with world coordinates and 1-based face indices.

    faces_local_idx are indices into verts_world (0-based).
    `usemtl`/`g` lines are omitted: geometry only, no material dependency.
    """
    lines = ["# " + h for h in header_lines]
    lines.append("# %d vertices, %d faces" % (len(verts_world), len(faces_local_idx)))
    for v in verts_world:
        lines.append("v %.9f %.9f %.9f" % (v[0], v[1], v[2]))
    for f in faces_local_idx:
        lines.append("f " + " ".join(str(int(i) + 1) for i in f))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return len(verts_world), len(faces_local_idx)


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--choice", action="append", required=True,
                    help="object:component_index, repeatable, in rank order")
    ap.add_argument("--support-objects", default="")
    ap.add_argument("--support-pad", type=float, default=0.6)
    ap.add_argument("--tag", default="")
    A = ap.parse_args(args)

    bpy.ops.wm.open_mainfile(filepath=A.blend)
    os.makedirs(A.outdir, exist_ok=True)
    sha = sha256_file(A.blend)

    choices = []
    for c in A.choice:
        obn, ci = c.rsplit(":", 1)
        choices.append((obn, int(ci)))

    manifest = {
        "script": "tools/v56/a_export_boards.py",
        "blend_file": A.blend,
        "blend_sha256": sha,
        "blender_version": bpy.app.version_string,
        "coordinate_system": {
            "units": "metres (scene unit = 1 m, see board_selection.json)",
            "up_axis": "OBJ is written in Blender's native Z-up right-handed frame",
            "world_coordinates_preserved": True,
            "note": ("vertices are the object's local vertices transformed by "
                     "matrix_world; no other transform is applied, so the OBJ "
                     "lands exactly where the source geometry sits in the scene"),
        },
        "exports": [],
    }

    # ---------------- board candidates ----------------
    for rank, (obn, ci) in enumerate(choices):
        ob = bpy.data.objects.get(obn)
        if ob is None or ob.type != "MESH":
            manifest["exports"].append({"error": "no such mesh object", "object": obn})
            continue
        me = ob.data
        wco, lco, mw = world_coords(ob)
        comp, order = components_of(me, len(me.vertices))
        if ci >= len(order):
            manifest["exports"].append({"error": "component index out of range",
                                        "object": obn, "component_index": ci,
                                        "available": len(order)})
            continue
        rt = order[ci]
        vids = [i for i in range(len(me.vertices)) if comp[i] == rt]
        fidx = [i for i, p in enumerate(me.polygons) if comp[p.vertices[0]] == rt]

        remap = {v: k for k, v in enumerate(vids)}
        verts = wco[vids]
        faces = [[remap[int(v)] for v in me.polygons[i].vertices] for i in fidx]

        objname = "board_%02d_%s_c%02d%s.obj" % (
            rank + 1, obn.replace(".", "_"), ci, ("_" + A.tag) if A.tag else "")
        objpath = os.path.join(A.outdir, objname)
        nv, nf = write_obj(objpath, verts, faces, [
            "V5.6 Hidden Alley can-board extraction",
            "source_blend=%s" % A.blend,
            "source_blend_sha256=%s" % sha,
            "source_object=%s" % obn,
            "component_index=%d (edge-connected component, rank %d)" % (ci, rank + 1),
            "rank=%d" % (rank + 1),
        ])

        mn, mx = verts.min(axis=0), verts.max(axis=0)
        # face areas + volume for the sidecar
        tri_area = 0.0
        for i in fidx:
            pv = [wco[int(v)] for v in me.polygons[i].vertices]
            a = np.zeros(3)
            for k in range(1, len(pv) - 1):
                a += np.cross(pv[k] - pv[0], pv[k + 1] - pv[0])
            tri_area += float(np.linalg.norm(a) / 2.0)

        sidecar = {
            "source_object": obn,
            "component_index": ci,
            "rank": rank + 1,
            "obj_file": objname,
            "obj_path": objpath,
            "source_blend": A.blend,
            "source_blend_sha256": sha,
            "object_matrix_world": [r(list(row)) for row in mw],
            "object_scale": r(list(ob.scale)),
            "object_location": r(list(ob.location)),
            "vertex_indices_used": [int(v) for v in vids],
            "face_indices_used": [int(f) for f in fidx],
            "n_vertices_exported": nv,
            "n_faces_exported": nf,
            "exported_world_aabb_min": r(list(mn)),
            "exported_world_aabb_max": r(list(mx)),
            "exported_world_dims": r(list(mx - mn)),
            "exported_face_area_m2": r(tri_area),
            "source_polygon_count_in_object": len(me.polygons),
            "materials_in_source": [m.name if m else None for m in me.materials],
        }
        with open(os.path.splitext(objpath)[0] + ".json", "w", encoding="utf-8") as fh:
            json.dump(sidecar, fh, indent=1)
        manifest["exports"].append(sidecar)
        print("[a_export] wrote %s (%d v, %d f)" % (objpath, nv, nf), flush=True)

    # ---------------- support geometry around the chosen board ----------------
    if choices:
        obn0, ci0 = choices[0]
        ob0 = bpy.data.objects.get(obn0)
        if ob0 is not None:
            wco0, _, _ = world_coords(ob0)
            comp0, order0 = components_of(ob0.data, len(ob0.data.vertices))
            rt0 = order0[ci0]
            vids0 = [i for i in range(len(ob0.data.vertices)) if comp0[i] == rt0]
            mn = wco0[vids0].min(axis=0) - A.support_pad
            mx = wco0[vids0].max(axis=0) + A.support_pad

            names = ([n.strip() for n in A.support_objects.split(",") if n.strip()]
                     if A.support_objects else list(DEFAULT_SUPPORT))
            sup_verts = []
            sup_faces = []
            used = []
            for nm in names:
                so = bpy.data.objects.get(nm)
                if so is None or so.type != "MESH":
                    manifest.setdefault("support_warnings", []).append(
                        "support object not found: %s" % nm)
                    continue
                swco, _, smw = world_coords(so)
                vmap = {}
                kept_f = []
                for p in so.data.polygons:
                    pv = [swco[int(v)] for v in p.vertices]
                    pa = np.array([min(q[k] for q in pv) for k in range(3)])
                    pb = np.array([max(q[k] for q in pv) for k in range(3)])
                    if not (pa[0] <= mx[0] and pb[0] >= mn[0] and
                            pa[1] <= mx[1] and pb[1] >= mn[1] and
                            pa[2] <= mx[2] and pb[2] >= mn[2]):
                        continue
                    face = []
                    for v in p.vertices:
                        v = int(v)
                        if v not in vmap:
                            vmap[v] = len(sup_verts)
                            sup_verts.append(swco[v])
                        face.append(vmap[v])
                    kept_f.append(face)
                if kept_f:
                    sup_faces.extend(kept_f)
                    used.append({"object": nm, "faces_kept": len(kept_f),
                                 "verts_kept": len(vmap),
                                 "world_matrix": [r(list(row)) for row in smw]})

            sup_name = "support_wall_ground%s.obj" % (("_" + A.tag) if A.tag else "")
            sup_path = os.path.join(A.outdir, sup_name)
            nv_s = nf_s = 0
            if sup_verts:
                nv_s, nf_s = write_obj(
                    sup_path, np.array(sup_verts), sup_faces,
                    ["V5.6 Hidden Alley can-board support geometry",
                     "source_blend=%s" % A.blend,
                     "source_blend_sha256=%s" % sha,
                     "clip_box_min=%s" % r(list(mn)),
                     "clip_box_max=%s" % r(list(mx)),
                     "chosen_board=%s component %d" % (obn0, ci0)])
                with open(os.path.splitext(sup_path)[0] + ".json", "w", encoding="utf-8") as fh:
                    json.dump({
                        "obj_file": sup_name,
                        "obj_path": sup_path,
                        "source_blend": A.blend,
                        "source_blend_sha256": sha,
                        "chosen_board_object": obn0,
                        "chosen_board_component": ci0,
                        "clip_pad_m": A.support_pad,
                        "clip_box_min": r(list(mn)),
                        "clip_box_max": r(list(mx)),
                        "contributing_objects": used,
                        "n_vertices_exported": nv_s,
                        "n_faces_exported": nf_s,
                    }, fh, indent=1)
                manifest["support_export"] = {
                    "obj_file": sup_name, "obj_path": sup_path,
                    "clip_pad_m": A.support_pad,
                    "clip_box_min": r(list(mn)), "clip_box_max": r(list(mx)),
                    "contributing_objects": used,
                    "n_vertices_exported": nv_s, "n_faces_exported": nf_s,
                }
                print("[a_export] wrote %s (%d v, %d f) from %d objects" %
                      (sup_path, nv_s, nf_s, len(used)), flush=True)
            else:
                manifest["support_export"] = {"error": "no support geometry in clip box"}
                print("[a_export] WARNING: no support geometry found", flush=True)

    with open(os.path.join(A.outdir, "export_manifest%s.json" %
                           (("_" + A.tag) if A.tag else "")), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    print("[a_export] done")


main()
