"""
a_board_components.py -- V5.6 Hidden Alley "can board" extraction, step 1.

Opens the Hidden Alley .blend, finds every object whose name starts with a
given prefix (default `wooden_boards`), splits each object's mesh into
edge-connected components, and reports per-component geometry:

  vertex / face / triangle counts, world-space AABB (min/max), box dimensions,
  total triangle area, signed (divergence-theorem) volume, bbox volume,
  PCA plane fit (normal + eigenvalues), dominant area-weighted face normal,
  tilt of that normal from world +Z, min/max Z.

Also dumps a compact world-AABB index of EVERY object in the scene so that
wall / ground support geometry can be selected offline without reloading the
481 MB file.

Run:
  & '<blender.exe>' --background --factory-startup --python a_board_components.py -- \
        --blend <scene.blend> --out <report.json> [--names wooden_boards]

Writes JSON only. Deletes nothing. Read-only w.r.t. the scene.
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time

import numpy as np

try:
    import bpy
except ImportError:  # pragma: no cover - only runs inside Blender
    print("This script must run inside Blender (needs bpy).", file=sys.stderr)
    raise


def log(*a):
    print("[a_components]", *a, flush=True)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def sha256_file(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def union_find(n):
    parent = list(range(n))
    rank = [0] * n

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1

    return find, union


def world_coords(obj):
    """Return (N,3) float64 numpy array of the mesh vertices in world space."""
    me = obj.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    out = co @ mw[:3, :3].T + mw[:3, 3]
    return out, co, mw


def tri_data(obj):
    """Return (tri_indices (T,3), tri_poly (T,)) using loop triangles."""
    me = obj.data
    me.calc_loop_triangles()
    lt = me.loop_triangles
    t = len(lt)
    idx = np.empty(t * 3, dtype=np.int32)
    lt.foreach_get("vertices", idx)
    idx = idx.reshape(t, 3)
    poly = np.empty(t, dtype=np.int32)
    lt.foreach_get("polygon_index", poly)
    return idx, poly


def poly_normals_world(obj, coords_world):
    """Area-weighted-ish: per-polygon world normal + area."""
    me = obj.data
    npoly = len(me.polygons)
    nrm = np.empty(npoly * 3, dtype=np.float64)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(npoly, 3)
    area = np.empty(npoly, dtype=np.float64)
    me.polygons.foreach_get("area", area)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    rot = mw[:3, :3]
    # normals transform with inverse-transpose; also normalise afterwards
    try:
        inv_t = np.linalg.inv(rot).T
    except np.linalg.LinAlgError:
        inv_t = rot
    nw = nrm @ inv_t.T
    ln = np.linalg.norm(nw, axis=1)
    ln[ln == 0] = 1.0
    nw = nw / ln[:, None]
    # area scale factor: Blender's polygon.area is in local space
    scale = np.linalg.norm(rot, axis=0)
    area_world = area * float(np.prod(scale)) if np.prod(scale) > 0 else area
    return nw, area_world


def signed_volume(coords, tris):
    """Divergence-theorem volume of a (hopefully closed) triangulated surface."""
    if len(tris) == 0:
        return 0.0
    v0 = coords[tris[:, 0]]
    v1 = coords[tris[:, 1]]
    v2 = coords[tris[:, 2]]
    return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)


def tri_areas(coords, tris):
    if len(tris) == 0:
        return np.zeros(0)
    v0 = coords[tris[:, 0]]
    v1 = coords[tris[:, 1]]
    v2 = coords[tris[:, 2]]
    return 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)


def pca_plane(coords):
    """Return (centroid, eigenvalues asc, eigenvectors as columns, normal)."""
    c = coords.mean(axis=0)
    d = coords - c
    cov = (d.T @ d) / max(len(coords), 1)
    w, v = np.linalg.eigh(cov)  # ascending
    return c, w, v


def deg(u, v):
    u = np.asarray(u, dtype=np.float64)
    v = np.asarray(v, dtype=np.float64)
    nu, nv = np.linalg.norm(u), np.linalg.norm(v)
    if nu == 0 or nv == 0:
        return 90.0
    c = float(np.clip(abs(np.dot(u, v)) / (nu * nv), -1.0, 1.0))
    return math.degrees(math.acos(c))


def r(x, nd=6):
    if x is None:
        return None
    if isinstance(x, (list, tuple)):
        return [r(v, nd) for v in x]
    try:
        f = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, nd)


def aabb_of(coords):
    return coords.min(axis=0), coords.max(axis=0)


def obj_world_aabb(obj):
    """AABB from mesh verts if available, else from bound_box corners."""
    if obj.type == "MESH" and len(obj.data.vertices) > 0:
        co, _, _ = world_coords(obj)
        mn, mx = aabb_of(co)
        return mn, mx
    mw = np.array(obj.matrix_world, dtype=np.float64)
    corners = np.array([list(c) for c in obj.bound_box], dtype=np.float64)
    corners = corners @ mw[:3, :3].T + mw[:3, 3]
    return corners.min(axis=0), corners.max(axis=0)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--names", default="wooden_boards")
    ap.add_argument("--aabb-index", default="")
    ap.add_argument("--connect-eps", type=float, default=0.0,
                    help="weld vertices closer than this (metres) before splitting "
                         "into connected components. 0 = pure edge connectivity.")
    A = ap.parse_args(args)

    t0 = time.time()
    report = {
        "script": "tools/v56/a_board_components.py",
        "blender_version": bpy.app.version_string,
        "blend_file": A.blend,
        "blend_size_bytes": os.path.getsize(A.blend) if os.path.exists(A.blend) else None,
        "blend_sha256": sha256_file(A.blend) if os.path.exists(A.blend) else None,
        "name_prefix_filter": A.names,
        "warnings": [],
    }
    log("sha256 computed in %.1fs" % (time.time() - t0))

    # ---------------- scene settings ----------------
    log("opening", A.blend)
    t1 = time.time()
    bpy.ops.wm.open_mainfile(filepath=A.blend)
    log("opened in %.1fs" % (time.time() - t1))

    sc = bpy.context.scene
    us = sc.unit_settings
    report["scene"] = {
        "name": sc.name,
        "unit_system": us.system,
        "scale_length": us.scale_length,
        "length_unit": us.length_unit,
        "frame_current": sc.frame_current,
        "frame_start": sc.frame_start,
        "frame_end": sc.frame_end,
        "render_engine": sc.render.engine,
        "resolution": [sc.render.resolution_x, sc.render.resolution_y],
        "resolution_percentage": sc.render.resolution_percentage,
        "active_camera": sc.camera.name if sc.camera else None,
    }
    if sc.camera:
        cam = sc.camera.data
        report["scene"]["camera"] = {
            "name": sc.camera.name,
            "type": cam.type,
            "lens_mm": getattr(cam, "lens", None),
            "sensor_width": getattr(cam, "sensor_width", None),
            "clip_start": cam.clip_start,
            "clip_end": cam.clip_end,
            "location": r(list(sc.camera.matrix_world.translation)),
        }
    log("unit system=%s scale_length=%s length_unit=%s" %
        (us.system, us.scale_length, us.length_unit))

    # ---------------- compact world-AABB index of the whole scene ----------------
    if A.aabb_index:
        idx = []
        for ob in bpy.data.objects:
            try:
                mn, mx = obj_world_aabb(ob)
            except Exception as e:  # noqa: BLE001
                report["warnings"].append("aabb failed for %s: %s" % (ob.name, e))
                continue
            nv = len(ob.data.vertices) if ob.type == "MESH" else None
            npo = len(ob.data.polygons) if ob.type == "MESH" else None
            entry = {
                "n": ob.name,
                "t": ob.type,
                "mn": r(list(mn), 4),
                "mx": r(list(mx), 4),
                "nv": nv,
                "nf": npo,
            }
            if ob.type == "MESH":
                mats = [m.name if m else None for m in ob.data.materials]
                if mats:
                    entry["mat"] = mats
            idx.append(entry)
        os.makedirs(os.path.dirname(A.aabb_index), exist_ok=True)
        with open(A.aabb_index, "w", encoding="utf-8") as fh:
            json.dump({
                "blend": A.blend,
                "count": len(idx),
                "objects": idx,
            }, fh, indent=1)
        log("wrote aabb index (%d objects) -> %s" % (len(idx), A.aabb_index))

    # ---------------- board objects ----------------
    targets = [ob for ob in bpy.data.objects if ob.name.startswith(A.names)]
    targets.sort(key=lambda o: o.name)
    log("matched %d objects: %s" % (len(targets), [o.name for o in targets]))
    if not targets:
        report["warnings"].append("no objects matched prefix %r" % A.names)

    objects_out = []
    comp_mode = "edge_connectivity"
    for ob in targets:
        t_ob = time.time()
        if ob.type != "MESH":
            report["warnings"].append("%s is type %s, skipped" % (ob.name, ob.type))
            continue
        me = ob.data
        coords, local_co, mw = world_coords(ob)
        tris, tri_poly = tri_data(ob)
        pareas = tri_areas(coords, tris) if len(tris) else np.zeros(0)
        pnormals, poly_areas = poly_normals_world(ob, coords)

        nv = len(me.vertices)
        find, union = union_find(nv)
        ne = len(me.edges)
        ev = np.empty(ne * 2, dtype=np.int32)
        me.edges.foreach_get("vertices", ev)
        ev = ev.reshape(ne, 2)
        comp_mode = "edge_connectivity"
        if A.connect_eps > 0.0:
            # provisionally weld: any two verts closer than eps are unioned
            eps2 = A.connect_eps * A.connect_eps
            order = np.argsort(coords[:, 1], kind="stable")
            cs = coords[order]
            for i in range(nv):
                j = i + 1
                while j < nv and (cs[j, 1] - cs[i, 1]) ** 2 <= eps2:
                    if ((cs[j] - cs[i]) ** 2).sum() <= eps2:
                        union(int(order[i]), int(order[j]))
                    j += 1
            comp_mode = "welded_eps_%g" % A.connect_eps
        for a, b in ev:
            union(int(a), int(b))
        roots = np.array([find(i) for i in range(nv)], dtype=np.int64)

        # edge -> number of incident faces (mesh quality / openness)
        edge_index = {}
        for ei, (a, b) in enumerate(ev):
            key = (int(min(a, b)), int(max(a, b)))
            edge_index[key] = ei
        edge_face_use = np.zeros(ne, dtype=np.int64)
        for p in me.polygons:
            pv = list(p.vertices)
            k = len(pv)
            for i in range(k):
                key = (int(min(pv[i], pv[(i + 1) % k])), int(max(pv[i], pv[(i + 1) % k])))
                ei = edge_index.get(key)
                if ei is not None:
                    edge_face_use[ei] += 1
        n_edgeuse = {}
        for c in edge_face_use.tolist():
            n_edgeuse[c] = n_edgeuse.get(c, 0) + 1

        # face -> component (via first vertex of the face)
        face_comp = np.empty(len(me.polygons), dtype=np.int64)
        for i, p in enumerate(me.polygons):
            face_comp[i] = roots[p.vertices[0]]

        # vertex degree (loose-vertex detection)
        vdeg = np.zeros(nv, dtype=np.int64)
        np.add.at(vdeg, ev[:, 0], 1)
        np.add.at(vdeg, ev[:, 1], 1)

        comp_ids = sorted(set(int(x) for x in roots))
        comps = []
        for ci, root in enumerate(comp_ids):
            vm = roots == root
            vids = np.nonzero(vm)[0]
            fidx = np.nonzero(face_comp == root)[0]
            fset = set(int(x) for x in fidx)
            tmask = np.array([int(p) in fset for p in tri_poly], dtype=bool) if len(tris) else np.zeros(0, dtype=bool)
            tidx = tris[tmask] if len(tris) else np.zeros((0, 3), dtype=np.int32)
            c = coords[vids]
            mn, mx = aabb_of(c)
            dims = mx - mn
            area = float(pareas[tmask].sum()) if len(pareas) else 0.0
            vol_signed = signed_volume(coords, tidx) if len(tidx) else 0.0
            bbox_vol = float(np.prod(np.maximum(dims, 0.0)))

            # PCA plane fit
            if len(vids) >= 3:
                cen, evals, evecs = pca_plane(c)
                normal = evecs[:, 0]  # smallest variance direction
                if normal[2] < 0:
                    normal = -normal
            else:
                cen = c.mean(axis=0) if len(c) else np.zeros(3)
                evals = np.zeros(3)
                evecs = np.eye(3)
                normal = np.array([0.0, 0.0, 1.0])

            # dominant face normal within this component (area weighted)
            if len(fidx) and len(pnormals):
                w = poly_areas[fidx]
                acc = (pnormals[fidx] * w[:, None]).sum(axis=0)
                n = np.linalg.norm(acc)
                dom = acc / n if n > 0 else np.zeros(3)
                if dom[2] < 0:
                    dom = -dom
            else:
                dom = np.zeros(3)

            # largest single face in the component
            if len(fidx):
                li = int(fidx[int(np.argmax(poly_areas[fidx]))])
                lf_area = float(poly_areas[li])
                lf_n = list(pnormals[li])
                if lf_n[2] < 0:
                    lf_n = [-x for x in lf_n]
            else:
                lf_area = 0.0
                lf_n = [0.0, 0.0, 0.0]

            # how planar: fraction of variance in the fitted plane
            tot_var = float(evals.sum())
            planarity = float(1.0 - evals[0] / tot_var) if tot_var > 0 else None

            comps.append({
                "component_index": ci,
                "root_vertex": int(root),
                "n_verts": int(len(vids)),
                "n_faces": int(len(fidx)),
                "n_tris": int(len(tidx)),
                "vertex_indices": [int(x) for x in vids],
                "face_indices": [int(x) for x in fidx],
                "loose_verts": int((vdeg[vids] == 0).sum()),
                "world_aabb_min": r(list(mn)),
                "world_aabb_max": r(list(mx)),
                "dims_xyz": r(list(dims)),
                "dims_sorted": r(sorted([float(d) for d in dims])),
                "center": r(list((mn + mx) / 2.0)),
                "centroid": r(list(cen)),
                "z_min": r(float(mn[2])),
                "z_max": r(float(mx[2])),
                "tri_area_total": r(area),
                "signed_volume": r(vol_signed),
                "abs_volume": r(abs(vol_signed)),
                "bbox_volume": r(bbox_vol),
                "pca_eigenvalues": r(list(evals), 10),
                "pca_normal": r(list(normal)),
                "pca_planarity": r(planarity),
                "dominant_face_normal": r(list(dom)),
                "dominant_normal_tilt_from_Z_deg": r(deg(dom, [0, 0, 1]), 4) if np.linalg.norm(dom) > 0 else None,
                "pca_normal_tilt_from_Z_deg": r(deg(normal, [0, 0, 1]), 4),
                "largest_face_area": r(lf_area),
                "largest_face_normal": r(lf_n),
                "largest_face_tilt_from_Z_deg": r(deg(lf_n, [0, 0, 1]), 4),
                "degenerate_flags": {
                    "zero_thickness": bool(min(float(d) for d in dims) < 1e-4),
                    "under_4_faces": bool(len(fidx) < 4),
                    "no_faces": bool(len(fidx) == 0),
                },
            })

        # pairwise AABB overlap between components
        overlaps = []
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                a0 = np.array(comps[i]["world_aabb_min"]); a1 = np.array(comps[i]["world_aabb_max"])
                b0 = np.array(comps[j]["world_aabb_min"]); b1 = np.array(comps[j]["world_aabb_max"])
                ov = np.maximum(0.0, np.minimum(a1, b1) - np.maximum(a0, b0))
                ovol = float(np.prod(ov))
                va = float(np.prod(np.maximum(a1 - a0, 0.0)))
                vb = float(np.prod(np.maximum(b1 - b0, 0.0)))
                smaller = min(va, vb)
                # touching / coplanar test: are min-gap distances tiny?
                gap = np.maximum(0.0, np.maximum(a0 - b1, b0 - a1))
                gaps = float(np.linalg.norm(gap))
                overlaps.append({
                    "a": i, "b": j,
                    "overlap_volume": r(ovol),
                    "frac_of_smaller_box": r(ovol / smaller) if smaller > 0 else None,
                    "aabb_gap_m": r(gaps),
                    "touching": bool(gaps < 1e-5),
                    "near": bool(gaps < 5e-3),
                })

        u_mn, u_mx = aabb_of(coords)
        objects_out.append({
            "name": ob.name,
            "type": ob.type,
            "parent": ob.parent.name if ob.parent else None,
            "matrix_world": [r(list(row)) for row in np.array(ob.matrix_world)],
            "location": r(list(ob.location)),
            "rotation_mode": ob.rotation_mode,
            "rotation_euler": r(list(ob.rotation_euler)),
            "rotation_quaternion": r(list(ob.rotation_quaternion)),
            "scale": r(list(ob.scale)),
            "dimensions_local_bbox": r(list(ob.dimensions)),
            "materials": [m.name if m else None for m in ob.data.materials],
            "modifiers": [{"name": m.name, "type": m.type} for m in ob.modifiers],
            "shape_keys": bool(ob.data.shape_keys),
            "vertex_groups": len(ob.vertex_groups),
            "hide_viewport": ob.hide_viewport,
            "hide_render": ob.hide_render,
            "has_animation": bool(ob.animation_data),
            "mesh": {
                "n_verts": nv,
                "n_edges": ne,
                "n_faces": len(me.polygons),
                "n_tris": int(len(tris)),
                "n_components_edge_connected": len(comps),
                "n_components_with_faces": sum(1 for c in comps if c["n_faces"] > 0),
                "n_components_loose_verts_only": sum(1 for c in comps if c["n_faces"] == 0),
                "n_loose_verts_total": int((vdeg == 0).sum()),
                "n_edges_used_by_1_face": n_edgeuse.get(1, 0),
                "n_edges_used_by_2_faces": n_edgeuse.get(2, 0),
                "n_edges_used_by_3plus_faces": sum(v for k, v in n_edgeuse.items() if k >= 3),
                "uv_layers": [uv.name for uv in me.uv_layers],
            },
            "object_world_aabb_min": r(list(u_mn)),
            "object_world_aabb_max": r(list(u_mx)),
            "object_world_dims": r(list(u_mx - u_mn)),
            "components": comps,
            "component_pair_overlaps": overlaps,
        })
        log("analysed %s: %d verts, %d faces, %d components (%.1fs)" %
            (ob.name, nv, len(me.polygons), len(comps), time.time() - t_ob))

    report["objects"] = objects_out
    report["component_mode"] = comp_mode
    report["connect_eps_m"] = A.connect_eps
    report["elapsed_s"] = r(time.time() - t0, 2)

    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    with open(A.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    log("wrote", A.out, "in %.1fs total" % (time.time() - t0))


main()
