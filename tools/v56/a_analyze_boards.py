"""a_analyze_boards.py -- V5.6 Hidden Alley board selection, step 2.

For each mesh-connected component of every `wooden_boards*` object this script
decides what the component physically IS and what it rests on / leans against.

It does NOT trust the AABB for dimensions: it recovers the three true slab edge
vectors from the component's own edges, verifies they are mutually
perpendicular (i.e. the component really is a rectangular slab) and reports
true length / width / thickness together with the lean from vertical.

Contact evidence is gathered with Blender's own BVH via scene.ray_cast
(downward for ground, sideways for wall) plus a triangle-triangle BVH overlap
test against a shortlist of scene objects whose AABB is near the component, so
"it intersects the wall" is a measurement, not an inference from AABBs.

Run:
  & '<blender.exe>' --background --factory-startup --python a_analyze_boards.py -- \
        --blend <scene.blend> --out <report.json> [--names wooden_boards] [--near 0.25]

Read-only w.r.t. the scene. Deletes nothing.
"""

import argparse
import json
import math
import os
import sys
import time

import numpy as np

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

DENSITIES = {"pine_low": 400.0, "softwood_mid": 500.0, "hardwood_high": 700.0}


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


def log(*a):
    print("[a_analyze]", *a, flush=True)


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


def edge_vectors(v):
    """Recover the three true slab edge vectors of a parallelepiped from its
    world-space corner set.

    All pairwise corner differences are clustered by direction (|cos|>0.999).
    Along each direction the SHORTEST segment is the primitive edge -- longer
    members of the same family are the face / body diagonals.  The three
    shortest direction families are the three edges of the parallelepiped; they
    are then checked for mutual orthogonality, which is what makes the slab a
    rectangular box rather than a sheared one.

    Returns (edges_sorted_desc_by_length, rectangular_flag, angles_deg,
             skew_check_dict).  Each edge is
    {"dir","len","len_min_family","len_max_family","n_parallel"}.
    """
    n = len(v)
    diffs = []
    for i in range(n):
        for j in range(i + 1, n):
            d = v[j] - v[i]
            L = float(np.linalg.norm(d))
            if L > 1e-12:
                diffs.append((L, d / L, d))
    clusters = []
    for L, u, d in sorted(diffs, key=lambda t: -t[0]):
        placed = False
        for c in clusters:
            if abs(float(np.dot(c["u"], u))) > 0.999:
                c["members"].append((L, d))
                placed = True
                break
        if not placed:
            clusters.append({"u": u, "members": [(L, d)]})
    fams = []
    for c in clusters:
        Ls = sorted(m[0] for m in c["members"])
        prim = min(c["members"], key=lambda m: m[0])
        fams.append({"dir": prim[1] / np.linalg.norm(prim[1]),
                     "len": prim[0],
                     "len_min_family": Ls[0],
                     "len_max_family": Ls[-1],
                     "n_parallel": len(Ls)})
    fams.sort(key=lambda f: f["len"])
    # pick the three shortest families that are mutually (near-)orthogonal
    chosen = []
    for f in fams:
        if all(abs(float(np.dot(f["dir"], g["dir"]))) < 0.02 for g in chosen):
            chosen.append(f)
        if len(chosen) == 3:
            break
    if len(chosen) < 3:
        return fams[:3], None, None, {"reason": "fewer than 3 orthogonal edge families"}
    angles = [math.degrees(math.acos(min(1.0, abs(float(np.dot(chosen[i]["dir"], chosen[j]["dir"]))))))
              for i, j in ((0, 1), (0, 2), (1, 2))]
    rect = bool(max(abs(a - 90.0) for a in angles) < 0.5)

    # skew check: can all corner points be written as origin + a*e1 + b*e2 + c*e3
    # with a,b,c in {0,1}?  If yes the component is a true rectangular slab.
    skew = {"checked": False}
    if len(v) == 8:
        m = np.array([chosen[0]["dir"] * chosen[0]["len"],
                      chosen[1]["dir"] * chosen[1]["len"],
                      chosen[2]["dir"] * chosen[2]["len"]]).T
        try:
            inv = np.linalg.inv(m)
            best = None
            for o in v:
                abc = (v - o) @ inv.T
                err = np.abs(abc - np.round(np.clip(abc, 0, 1))).max()
                if best is None or err < best:
                    best = err
            skew = {"checked": True, "max_corner_parametric_error": float(best),
                    "corner_error_m": float(best) * float(min(f["len"] for f in chosen)),
                    "is_exact_box": bool(best < 1e-4)}
        except np.linalg.LinAlgError:
            skew = {"checked": False, "reason": "singular edge basis"}
    chosen.sort(key=lambda f: -f["len"])
    return chosen, rect, angles, skew


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--names", default="wooden_boards")
    ap.add_argument("--aabb-index", default="")
    ap.add_argument("--near", type=float, default=0.25,
                    help="AABB proximity used to shortlist contact-test objects")
    A = ap.parse_args(args)

    t0 = time.time()
    bpy.ops.wm.open_mainfile(filepath=A.blend)
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()

    idx = None
    if A.aabb_index and os.path.exists(A.aabb_index):
        idx = json.load(open(A.aabb_index, encoding="utf-8"))["objects"]

    targets = sorted([o for o in bpy.data.objects if o.name.startswith(A.names)],
                     key=lambda o: o.name)

    # ---- precompute world AABB for every mesh (cheap enough here) ----------
    all_aabb = {}
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        try:
            mw = np.array(ob.matrix_world, dtype=np.float64)
            n = len(ob.data.vertices)
            if n == 0:
                continue
            co = np.empty(n * 3, dtype=np.float64)
            ob.data.vertices.foreach_get("co", co)
            co = co.reshape(n, 3) @ mw[:3, :3].T + mw[:3, 3]
            all_aabb[ob.name] = (co.min(axis=0), co.max(axis=0), ob, mw)
        except Exception:
            continue
    log("indexed %d mesh AABBs" % len(all_aabb))

    report = {
        "script": "tools/v56/a_analyze_boards.py",
        "blend": A.blend,
        "blender": bpy.app.version_string,
        "scene": sc.name,
        "unit_settings": {
            "system": sc.unit_settings.system,
            "scale_length": sc.unit_settings.scale_length,
            "length_unit": sc.unit_settings.length_unit,
        },
        "densities_kg_m3": DENSITIES,
        "objects": [],
        "warnings": [],
    }

    # ---------- unit-scale corroboration (metre-sized set dressing) ----------
    dims_all = []
    for nm, (mn, mx, ob, mw) in all_aabb.items():
        dims_all.append(float(np.max(mx - mn)))
    dims_all = np.array(dims_all)
    report["unit_scale_evidence"] = {
        "n_mesh_objects": int(len(dims_all)),
        "max_dim_units_percentiles": {
            "p10": r(float(np.percentile(dims_all, 10)), 5),
            "p50": r(float(np.percentile(dims_all, 50)), 5),
            "p90": r(float(np.percentile(dims_all, 90)), 5),
            "p99": r(float(np.percentile(dims_all, 99)), 5),
            "max": r(float(dims_all.max()), 5),
        },
        "n_objects_over_100_units": int((dims_all > 100).sum()),
        "n_objects_under_20_units": int((dims_all < 20).sum()),
        "non_unit_scale_objects": [],
        "camera_clip": [sc.camera.data.clip_start, sc.camera.data.clip_end] if sc.camera else None,
        "note": ("scale_length is a Blender display factor, not a geometry scale; "
                 "the metre claim is supported by the set-dressing size distribution "
                 "and the camera near-clip, and is corroborated by the physics check "
                 "that a real can diameter is a plausible fraction of the board."),
    }
    for ob in bpy.data.objects:
        s = np.array(ob.scale, dtype=np.float64)
        if not np.allclose(s, 1.0, atol=1e-4) and ob.type == "MESH" and ob.name in all_aabb:
            d = all_aabb[ob.name][1] - all_aabb[ob.name][0]
            report["unit_scale_evidence"]["non_unit_scale_objects"].append({
                "name": ob.name, "scale": r(list(s)),
                "world_dims": r(list(d)), "max_dim": r(float(d.max())),
            })
    report["unit_scale_evidence"]["n_non_unit_scale_mesh"] = len(
        report["unit_scale_evidence"]["non_unit_scale_objects"])

    for ob in targets:
        me = ob.data
        nv = len(me.vertices)
        co = np.empty(nv * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(nv, 3)
        mw = np.array(ob.matrix_world, dtype=np.float64)
        wco = co @ mw[:3, :3].T + mw[:3, 3]

        comp, order = components_of(me, nv)
        # face -> component, tri -> component
        f2c = np.empty(len(me.polygons), dtype=np.int64)
        for i, p in enumerate(me.polygons):
            f2c[i] = comp[p.vertices[0]]
        me.calc_loop_triangles()
        lt = me.loop_triangles
        tri = np.empty(len(lt) * 3, dtype=np.int32)
        lt.foreach_get("vertices", tri)
        tri = tri.reshape(-1, 3)
        t2p = np.empty(len(lt), dtype=np.int32)
        lt.foreach_get("polygon_index", t2p)

        # world area scale for this object's polygons
        sx = np.linalg.norm(mw[:3, :3], axis=0)
        area_scale = float(np.prod(sx))  # placeholder, replaced below
        # correct area scale: local area -> world area is |det| * ||inv^T n|| relation;
        # for a similarity transform (uniform s) it is s^2. Use the general
        # formula per polygon via the cross product instead (exact).
        recs = []
        for ci, rt in enumerate(order):
            vids = [i for i in range(nv) if comp[i] == rt]
            fidx = [i for i in range(len(me.polygons)) if f2c[i] == rt]
            tmask = np.array([f2c[int(p)] == rt for p in t2p], dtype=bool)
            tris = tri[tmask]
            c = wco[vids]
            mn, mx = c.min(axis=0), c.max(axis=0)

            # exact world triangle areas
            v0, v1, v2 = wco[tris[:, 0]], wco[tris[:, 1]], wco[tris[:, 2]]
            tareas = 0.5 * np.linalg.norm(np.cross(v1 - v0, v2 - v0), axis=1)
            area = float(tareas.sum())
            vol = float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)

            ev, rect_ok, perp, skew = edge_vectors(c) if len(c) >= 2 else ([], None, None, {})
            dims_true = [e["len"] for e in ev][:3]

            # ---- is this component a CLOSED solid or an open shell? ----------
            # The divergence-theorem volume is only meaningful for a closed
            # surface.  These components turn out to be 5-face boxes (one face
            # dropped), so the signed volume must NOT be used as a volume.
            edge_use_c = {}
            for fi in fidx:
                pv = list(me.polygons[fi].vertices)
                k = len(pv)
                for i in range(k):
                    key = (int(min(pv[i], pv[(i + 1) % k])), int(max(pv[i], pv[(i + 1) % k])))
                    edge_use_c[key] = edge_use_c.get(key, 0) + 1
            n_boundary_edges = sum(1 for v in edge_use_c.values() if v == 1)
            is_closed = bool(n_boundary_edges == 0)
            # the boundary loop is the rim of the missing face; report where it is
            open_face = None
            if n_boundary_edges:
                bverts = sorted({i for k2, v in edge_use_c.items() if v == 1 for i in k2})
                bc = wco[bverts]
                open_face = {
                    "boundary_edge_count": int(n_boundary_edges),
                    "boundary_vertex_count": int(len(bverts)),
                    "boundary_vertex_indices": [int(i) for i in bverts],
                    "boundary_aabb_min": r(list(bc.min(axis=0))),
                    "boundary_aabb_max": r(list(bc.max(axis=0))),
                    "boundary_dims": r(list(bc.max(axis=0) - bc.min(axis=0))),
                    "boundary_centroid": r(list(bc.mean(axis=0))),
                    "missing_face_outward_axis": (
                        "the thickness-normal direction the shell is open toward"),
                }

            # volume: exact only if closed; otherwise the verified box volume
            box_vol = float(np.prod(dims_true)) if len(dims_true) == 3 else None
            volume = box_vol if (box_vol is not None and not is_closed) else abs(vol)
            volume_basis = ("verified rectangular-slab box volume L*W*T (component is an "
                            "open 5-face shell, so the divergence-theorem volume is not "
                            "applicable)") if not is_closed else "signed divergence-theorem volume"

            # largest face of the component (the slab's broad face)
            if fidx:
                big = max(fidx, key=lambda i: me.polygons[i].area)
                bn = np.array(me.polygons[big].normal, dtype=np.float64)
                bn = np.linalg.inv(mw[:3, :3]).T @ bn
                bn = bn / np.linalg.norm(bn)
                if bn[0] < 0:
                    bn = -bn
                # exact world area of that polygon
                pv = list(me.polygons[big].vertices)
                a = np.zeros(3)
                for k in range(1, len(pv) - 1):
                    a += np.cross(wco[pv[k]] - wco[pv[0]], wco[pv[k + 1]] - wco[pv[0]])
                big_area = float(np.linalg.norm(a) / 2.0)
            else:
                bn = np.zeros(3)
                big_area = 0.0
                big = None

            # ---- the slab's six face roles, chosen by world geometry ----------
            # The faces are named by MEASURED world orientation, not by the
            # local axis they happen to lie on:
            #   base_face  = the face whose outward normal is most downward (-Z)
            #   top_face   = the face whose outward normal is most upward (+Z)
            #   wall_face  = the face whose outward normal is most toward -X
            #                (the apartment wall plane sits at x = -2.2)
            # For a board lying on the ground the base face is a broad face; for
            # a board standing on its end the base face is a thin end face.  The
            # naming is derived, so it stays correct either way.
            def face_world_normal(i):
                nn = np.array(me.polygons[i].normal, dtype=np.float64)
                nn = np.linalg.inv(mw[:3, :3]).T @ nn
                n = np.linalg.norm(nn)
                return nn / n if n > 0 else nn

            face_roles = {}
            base_face = top_face = wall_face = None
            if fidx:
                nrm = {i: face_world_normal(i) for i in fidx}
                base_face = min(fidx, key=lambda i: float(nrm[i][2]))
                top_face = max(fidx, key=lambda i: float(nrm[i][2]))
                wall_face = min(fidx, key=lambda i: float(nrm[i][0]))
                face_roles = {
                    "base_face": {"polygon_index": int(base_face),
                                  "world_normal": r(list(nrm[base_face])),
                                  "downward_alignment": r(float(-nrm[base_face][2]), 5)},
                    "top_face": {"polygon_index": int(top_face),
                                 "world_normal": r(list(nrm[top_face])),
                                 "upward_alignment": r(float(nrm[top_face][2]), 5)},
                    "wall_face": {"polygon_index": int(wall_face),
                                  "world_normal": r(list(nrm[wall_face])),
                                  "toward_wall_alignment": r(float(-nrm[wall_face][0]), 5),
                                  "note": "most -X facing face; the apartment wall "
                                          "plane is at x = -2.2"},
                }
                # an end face is one whose normal is close to the long axis
                if ev:
                    longdir = ev[0]["dir"]
                    ends = sorted(fidx, key=lambda i: abs(float(np.dot(nrm[i], longdir))),
                                  reverse=True)[:2]
                    face_roles["end_faces"] = [
                        {"polygon_index": int(i), "world_normal": r(list(nrm[i])),
                         "alignment_with_long_axis": r(abs(float(np.dot(nrm[i], longdir))), 5)}
                        for i in ends]

                # classify EVERY face by which slab axis its normal follows,
                # and note whether a broad face is missing (open shell).  This
                # is unambiguous where the base/top/wall role labels are not.
                axes = [("longest_edge", ev[0]["dir"]),
                        ("middle_edge", ev[1]["dir"]),
                        ("thickness_edge", ev[2]["dir"])] if len(ev) == 3 else []
                fct = []
                for i in fidx:
                    row = {"polygon_index": int(i),
                           "world_normal": r(list(nrm[i]))}
                    if axes:
                        best = max(axes, key=lambda ax: abs(float(np.dot(nrm[i], ax[1]))))
                        row["normal_follows"] = best[0]
                        row["alignment"] = r(abs(float(np.dot(nrm[i], best[1]))), 5)
                        row["points_toward"] = "+X" if nrm[i][0] > 0 else "-X"
                    pvv = list(me.polygons[i].vertices)
                    acc = np.zeros(3)
                    for k in range(1, len(pvv) - 1):
                        acc += np.cross(wco[pvv[k]] - wco[pvv[0]],
                                        wco[pvv[k + 1]] - wco[pvv[0]])
                    row["world_area_m2"] = r(float(np.linalg.norm(acc) / 2.0), 8)
                    fct.append(row)
                face_roles["face_classification"] = fct
                # is a broad face (normal along the thickness axis) missing?
                if len(ev) == 3:
                    broad = [x for x in fct
                             if x.get("normal_follows") == "thickness_edge"]
                    face_roles["broad_faces_present"] = len(broad)
                    face_roles["broad_faces_missing"] = max(0, 2 - len(broad))
                    face_roles["open_side_note"] = (
                        "a 5-face shell is open on one broad side; the missing "
                        "broad face cannot be used as a wall-contact probe origin")

            # ---- contact probes -------------------------------------------
            # Probes are labelled by ROLE (base / top / wall face) so the labels
            # mean the same thing for a board standing up and a board lying down.
            probes = []
            origin_sets = []
            if base_face is not None:
                pv = list(me.polygons[base_face].vertices)
                bc = wco[pv].mean(axis=0)
                origin_sets.append(("base_face_centroid_down", bc, (0, 0, -1)))
                # the lowest vertex of the base face -- the true resting corner
                low = wco[pv][np.argmin(wco[pv][:, 2])]
                origin_sets.append(("base_face_lowest_vertex_down", low, (0, 0, -1)))
                for d in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0)):
                    origin_sets.append(("base_face_centroid_dir%s" % (d,), bc, d))
            if top_face is not None:
                pv = list(me.polygons[top_face].vertices)
                tc = wco[pv].mean(axis=0)
                origin_sets.append(("top_face_centroid_down", tc, (0, 0, -1)))
                origin_sets.append(("top_face_centroid_up", tc, (0, 0, 1)))
                for d in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0)):
                    origin_sets.append(("top_face_centroid_dir%s" % (d,), tc, d))
                origin_sets.append(("top_face_wallward", tc, (-1, 0, 0)))
            if wall_face is not None:
                pv = list(me.polygons[wall_face].vertices)
                wc = wco[pv].mean(axis=0)
                origin_sets.append(("wall_face_centroid_wallward", wc, (-1, 0, 0)))
                origin_sets.append(("wall_face_centroid_awayfromwall", wc, (1, 0, 0)))
            # the VERTEX closest to the wall (smallest x), cast toward the wall.
            # This is the most reliable wall-gap measurement: it starts from a
            # point guaranteed to be on the component's actual surface, so it
            # works even when the component's open side faces the wall and the
            # centroid-based probes exit through the missing face.
            near_wall_v = c[int(np.argmin(c[:, 0]))]
            origin_sets.append(("nearest_wall_vertex_wallward", near_wall_v, (-1, 0, 0)))
            far_wall_v = c[int(np.argmax(c[:, 0]))]
            origin_sets.append(("farthest_wall_vertex_wallward", far_wall_v, (-1, 0, 0)))
            origin_sets.append(("farthest_wall_vertex_awayfromwall", far_wall_v, (1, 0, 0)))
            cen = (mn + mx) / 2.0
            origin_sets.append(("centroid_down", cen, (0, 0, -1)))
            origin_sets.append(("centroid_up", cen, (0, 0, 1)))
            # the highest and lowest VERTICES of the whole component, ray-cast
            # in the four cardinal horizontal directions, plus down from the
            # lowest one.  These four rays answer "what is physically touching
            # the board's top and bottom ends" without relying on face labels.
            lo_v = c[int(np.argmin(c[:, 2]))]
            hi_v = c[int(np.argmax(c[:, 2]))]
            for d in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1)):
                origin_sets.append(("lowest_vertex_dir%s" % (d,), lo_v, d))
            for d in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, 1)):
                origin_sets.append(("highest_vertex_dir%s" % (d,), hi_v, d))
            # sample a grid of points on the broad face and cast toward the wall
            if big is not None:
                pv = list(me.polygons[big].vertices)
                fp = wco[pv]
                for frac in ((0.5, 0.1), (0.5, 0.5), (0.5, 0.9), (0.1, 0.5), (0.9, 0.5)):
                    p = fp[0] + frac[0] * (fp[1] - fp[0]) + frac[1] * (fp[3] - fp[0])
                    origin_sets.append(("broad_face%.1f_%.1f_wallward" % frac, p, (-1, 0, 0)))
            seen = set()
            for name, o, d in origin_sets:
                if name in seen:
                    continue
                seen.add(name)
                od = np.array(d, dtype=np.float64)
                od = od / np.linalg.norm(od)
                res = sc.ray_cast(dg, Vector([float(x) for x in o]), Vector([float(x) for x in od]))
                rec = {"probe": name,
                       "origin": r(list(o)),
                       "direction": r(list(od)),
                       "hit": bool(res[0])}
                if res[0]:
                    loc = np.array(res[1], dtype=np.float64)
                    rec["hit_object"] = res[4].name if res[4] else None
                    rec["hit_location"] = r(list(loc))
                    rec["hit_distance_m"] = r(float(np.linalg.norm(loc - o)))
                    rec["hit_normal"] = r(list(res[2]))
                probes.append(rec)

            # ---- triangle-triangle intersection with nearby objects -------
            # build the component's world triangles once
            polys = [list(map(int, t)) for t in tris]
            comp_pts = [tuple(map(float, p)) for p in wco]
            inter = []
            if polys:
                shortlist = []
                for nm, (omn, omx, oob, omw) in all_aabb.items():
                    if nm == ob.name:
                        continue
                    # AABB near-test
                    gap = np.maximum(0.0, np.maximum(omn - mx, mn - omx))
                    if float(np.linalg.norm(gap)) <= A.near:
                        shortlist.append((nm, oob, omw))
                for nm, oob, omw in shortlist:
                    try:
                        if len(oob.data.vertices) > 300000:
                            continue
                        # bring the component into the target's local space
                        inv = np.linalg.inv(omw)
                        pts_local = [tuple(map(float, (inv[:3, :3] @ np.array(p) + inv[:3, 3])))
                                     for p in comp_pts]
                        a = BVHTree.FromPolygons(pts_local, polys, all_triangles=False, epsilon=0.0)
                        b = BVHTree.FromObject(oob, dg)
                        ov = a.overlap(b)
                        if ov:
                            inter.append({"object": nm, "overlapping_tri_pairs": len(ov),
                                          "triangles_involved": min(len(ov), 12),
                                          "min_penetration_probe": r(list(ov[0]))})
                    except Exception as e:  # noqa: BLE001
                        report["warnings"].append("overlap %s/%s failed: %s" % (ob.name, nm, e))

            # ---- distance to the other components of this object ----------
            others = []
            for cj, rt2 in enumerate(order):
                if rt2 == rt:
                    continue
                oj = [i for i in range(nv) if comp[i] == rt2]
                dmin = float(np.linalg.norm(wco[vids][:, None, :] - wco[oj][None, :, :], axis=2).min())
                others.append({"component_index": cj, "min_vertex_distance_m": r(dmin)})

            # ---- camera visibility (which components a can shot could see) ---
            vis = None
            if sc.camera:
                try:
                    from bpy_extras.object_utils import world_to_camera_view
                    cam = sc.camera
                    pts = []
                    for sx in (mn[0], mx[0]):
                        for sy in (mn[1], mx[1]):
                            for sz in (mn[2], mx[2]):
                                p = world_to_camera_view(sc, cam, Vector((float(sx), float(sy), float(sz))))
                                pts.append((p.x, p.y, p.z))
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    zs = [p[2] for p in pts]
                    cx0, cy0 = max(0.0, min(xs)), max(0.0, min(ys))
                    cx1, cy1 = min(1.0, max(xs)), min(1.0, max(ys))
                    clipped = max(0.0, cx1 - cx0) * max(0.0, cy1 - cy0)
                    vis = {
                        "camera": cam.name,
                        "ndc_bbox": r([min(xs), min(ys), max(xs), max(ys)], 5),
                        "ndc_depth_min": r(min(zs), 5),
                        "in_front_of_camera": bool(min(zs) > 0),
                        "in_frame": bool(max(xs) > 0 and min(xs) < 1 and
                                         max(ys) > 0 and min(ys) < 1 and min(zs) > 0),
                        "clipped_frame_area_fraction": r(clipped, 6),
                    }
                except Exception as e:  # noqa: BLE001
                    report["warnings"].append("projection failed for %s c%d: %s" % (ob.name, ci, e))

            # dims_true is sorted descending: [longest, middle, shortest].
            # "thickness" is the SHORTEST edge -- the thin direction of the
            # board.  "length"/"height" are the other two.  Which of those two
            # is vertical in world space is answered by the world orientation
            # block, not guessed here.
            #
            # LEAN FROM VERTICAL is defined as the tilt of the slab's IN-PLANE
            # axis that is nearest to world vertical (its "height" direction).
            # Equivalently, for a rectangular slab, it is
            #   90 deg - (tilt of the thickness axis from vertical).
            # An upright board has thickness horizontal -> lean 0.
            lean = None
            if len(ev) == 3:
                inplane = [ev[0]["dir"], ev[1]["dir"]]
                up_axis = max(inplane, key=lambda d: abs(float(d[2])))
                lean = math.degrees(math.acos(min(1.0, abs(float(up_axis[2])))))
            elif len(ev) == 2:
                lean = math.degrees(math.acos(min(1.0, abs(float(ev[0]["dir"][2])))))
            long_tilt = None
            if ev:
                long_tilt = math.degrees(math.acos(min(1.0, abs(float(ev[0]["dir"][2])))))

            # mass: volume x density, three plausible wood densities
            mass = {k: r(volume * d, 5) for k, d in DENSITIES.items()}

            # ---- toppling geometry (a MEASUREMENT, not a topple prediction) --
            # For a rigid slab propped at angle theta from vertical, the moment
            # arm about its lower resting edge is h*sin(theta) where h is the
            # height of the centre of mass, and the restoring arm is
            # (t/2)*cos(theta).  These are pure geometry; whether a can can
            # supply the required impulse is a separate physics question that
            # this script does NOT answer.
            topple = None
            if len(dims_true) == 3:
                T = dims_true[2]
                theta = math.radians(lean) if lean is not None else None
                # height of the component's centre above its own lowest point
                com_z = float(c[:, 2].mean())
                h = com_z - float(mn[2])
                if theta is not None:
                    # the board leans toward the wall (-X); the sign of the lean
                    # direction is taken from the wall_face normal
                    lean_dir = -1.0 if (wall_face is not None and
                                        float(nrm[wall_face][0]) < 0) else 1.0
                    topple = {
                        "lean_from_vertical_deg": r(lean, 4),
                        "thickness_m": r(T),
                        "com_height_above_lowest_point_m": r(h),
                        "height_of_tallest_vertex_above_lowest_m": r(float(mx[2] - mn[2])),
                        "restoring_arm_t_over_2_cos_theta_m": r((T / 2.0) * math.cos(theta), 6),
                        "lean_arm_h_sin_theta_m": r(h * math.sin(theta), 6),
                        "static_tip_angle_deg": r(math.degrees(math.atan2(T, 2.0 * h)), 4),
                        "leans_toward_wall_negative_X": bool(lean_dir < 0),
                        "note": ("static_tip_angle is the lean angle at which the "
                                 "centre of mass passes over the resting edge; these "
                                 "numbers describe geometry only and do NOT predict "
                                 "whether a can topples the board"),
                    }

            slab_reading = None
            if len(dims_true) == 3:
                L, W, T = dims_true
                slab_reading = {
                    "longest_edge_m": r(L),
                    "middle_edge_m": r(W),
                    "shortest_edge_m": r(T),
                    "thickness_m": r(T),
                    "thickness_axis_world_dir": r(list(ev[2]["dir"])) if len(ev) == 3 else None,
                    "thickness_axis_tilt_from_vertical_deg": (
                        r(math.degrees(math.acos(min(1.0, abs(float(ev[2]["dir"][2]))))), 4)
                        if len(ev) == 3 else None),
                    "longest_axis_world_dir": r(list(ev[0]["dir"])) if ev else None,
                    "longest_axis_tilt_from_vertical_deg": r(long_tilt, 4),
                    "aspect_length_over_thickness": r(L / T) if T > 0 else None,
                    "fits_real_plank_range": bool(
                        0.008 <= T <= 0.06 and 0.15 <= W and L <= 4.0) if T > 0 else None,
                }

            # world-frame orientation: the three true edge unit vectors in world
            # coordinates, expressed as tilt from each world axis.  This is the
            # only orientation report that does not depend on local axes.
            orient = None
            if len(ev) == 3:
                axes = ["+X", "+Y", "+Z"]
                mat = np.array([e["dir"] for e in ev], dtype=np.float64)  # 3x3, rows
                orient = {
                    "signed_edge_vectors_world": [
                        {"len_m": r(e["len"]), "dir": r(list(e["dir"]))} for e in ev],
                    "abs_dot_with_world_axes": [
                        [r(abs(float(np.dot(e["dir"], ax))), 5) for ax in np.eye(3)]
                        for e in ev],
                    "assignment_by_abs_dot_lt_1e-3": {},
                }
                for i, e in enumerate(ev):
                    for k, ax in enumerate(axes):
                        if abs(float(np.dot(e["dir"], np.eye(3)[k]))) < 1e-3:
                            orient["assignment_by_abs_dot_lt_1e-3"].setdefault(ax, []).append(
                                {"edge_len_m": r(e["len"]), "idx": i})
            recs.append({
                "component_index": ci,
                "n_verts": len(vids),
                "n_faces": len(fidx),
                "n_tris": int(tmask.sum()),
                "vertex_indices": vids,
                "face_indices": fidx,
                "world_aabb_min": r(list(mn)),
                "world_aabb_max": r(list(mx)),
                "world_aabb_dims": r(list(mx - mn)),
                "slab_edge_vectors": [
                    {"dir": r(list(e["dir"])), "len_m": r(e["len"]),
                     "len_min_family_m": r(e["len_min_family"]),
                     "len_max_family_m": r(e["len_max_family"]),
                     "n_parallel_differences": e["n_parallel"]} for e in ev[:4]],
                "is_rectangular_slab": rect_ok,
                "edge_perpendicularity_angles_deg": r(perp, 4),
                "box_skew_check": {k: (r(vv) if isinstance(vv, float) else vv)
                                   for k, vv in skew.items()},
                "true_dims_length_width_thickness_m": r(sorted(dims_true, reverse=True)),
                "parallelepiped_volume_m3": r(float(np.prod(dims_true)) if len(dims_true) == 3 else None),
                "assumed_thickness_axis_normal": r(list(bn)),
                "broad_face_area_m2": r(big_area),
                "broad_face_polygon_index": big,
                "surface_area_m2": r(area),
                "signed_volume_m3": r(vol),
                "abs_volume_m3": r(abs(vol)),
                "is_closed_solid": is_closed,
                "boundary_edge_count": int(n_boundary_edges),
                "open_face": open_face,
                "volume_m3": r(volume),
                "volume_basis": volume_basis,
                "slab_box_volume_m3": r(box_vol),
                "slab_reading": slab_reading,
                "mass_kg": mass,
                "mass_basis": ("mass = volume x density, volume = %s; three wood "
                               "densities are reported (pine ~400, softwood ~500, "
                               "hardwood ~700 kg/m3) because the material texture does "
                               "not fix the species" % volume_basis),
                "lean_from_vertical_deg": r(lean, 4),
                "long_axis_tilt_from_vertical_deg": r(long_tilt, 4),
                "world_orientation": orient,
                "face_roles": face_roles,
                "camera_visibility": vis,
                "toppling_geometry": topple,
                "lowest_vertex_world": r(list(c[int(np.argmin(c[:, 2]))])),
                "highest_vertex_world": r(list(c[int(np.argmax(c[:, 2]))])),
                "z_min": r(float(mn[2])), "z_max": r(float(mx[2])),
                "height_m": r(float(mx[2] - mn[2])),
                "contact_probes": probes,
                "triangle_intersections_with_nearby_objects": inter,
                "min_distance_to_other_components": others,
            })
        report["objects"].append({
            "name": ob.name,
            "matrix_world": [r(list(row)) for row in mw],
            "scale": r(list(ob.scale)),
            "location": r(list(ob.location)),
            "rotation_euler": r(list(ob.rotation_euler)),
            "materials": [m.name if m else None for m in ob.data.materials],
            "modifiers": [{"name": m.name, "type": m.type} for m in ob.modifiers],
            "n_verts": nv, "n_edges": len(me.edges), "n_faces": len(me.polygons),
            "n_components": len(order),
            "components": recs,
        })
        log("analysed %s (%d comps)" % (ob.name, len(order)))

    report["elapsed_s"] = r(time.time() - t0, 2)
    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    json.dump(report, open(A.out, "w", encoding="utf-8"), indent=1)
    log("wrote", A.out)


main()
