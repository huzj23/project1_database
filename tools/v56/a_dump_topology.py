"""a_dump_topology.py -- V5.6 dump raw vertex/face topology for wooden_boards*.

Prints, for each matched object: every vertex (index, local co, world co,
connected component) and every face (index, vertex indices, world area,
world normal, component). Also prints the edges and their face-use count, so
the true shape of each connected component can be read off by hand.

Writes a text report; read-only w.r.t. the scene.

Run:
  & '<blender.exe>' --background --factory-startup --python a_dump_topology.py -- \
        --blend <scene.blend> --out <report.txt> [--names wooden_boards]
"""

import argparse
import json
import os
import sys

import numpy as np

import bpy


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--names", default="wooden_boards")
    A = ap.parse_args(args)

    bpy.ops.wm.open_mainfile(filepath=A.blend)
    lines = []

    def w(s=""):
        lines.append(s)

    for ob in sorted([o for o in bpy.data.objects if o.name.startswith(A.names)],
                     key=lambda o: o.name):
        me = ob.data
        mw = np.array(ob.matrix_world, dtype=np.float64)
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(n, 3)
        wco = co @ mw[:3, :3].T + mw[:3, 3]

        # connected components by edges
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for e in me.edges:
            a, b = find(e.vertices[0]), find(e.vertices[1])
            if a != b:
                parent[a] = b
        comp = [find(i) for i in range(n)]
        roots = sorted(set(comp))
        cid = {r: i for i, r in enumerate(roots)}

        w("=" * 110)
        w("OBJECT %s   verts=%d edges=%d faces=%d   matrix_world=" % (ob.name, n, len(me.edges), len(me.polygons)))
        for row in mw:
            w("    [%s]" % "  ".join("% .9f" % v for v in row))
        w("")
        w("--- VERTICES (idx  component  local x y z   world x y z) ---")
        for i in range(n):
            w("  v%-3d c%-2d  L(% .6f % .6f % .6f)  W(% .6f % .6f % .6f)" % (
                i, cid[comp[i]], co[i, 0], co[i, 1], co[i, 2], wco[i, 0], wco[i, 1], wco[i, 2]))
        w("")
        w("--- FACES (idx  component  nverts  vertex indices  world area  world normal  tilt_from_Z) ---")
        for pi, p in enumerate(me.polygons):
            pv = list(p.vertices)
            nl = np.array(p.normal, dtype=np.float64)
            try:
                nw = np.linalg.inv(mw[:3, :3]).T @ nl
            except np.linalg.LinAlgError:
                nw = nl
            ln = np.linalg.norm(nw)
            nw = nw / ln if ln else nw
            sc = float(np.prod(np.linalg.norm(mw[:3, :3], axis=0)))
            ang = np.degrees(np.arccos(min(1.0, abs(nw[2])))) if ln else 90.0
            w("  f%-3d c%-2d  nv=%d  %-28s  A=%.6f  N(% .4f % .4f % .4f)  tilt=%6.2f" % (
                pi, cid[comp[pv[0]]], len(pv), str(pv), p.area * sc,
                nw[0], nw[1], nw[2], ang))
        w("")
        w("--- EDGES (idx  verts  n_faces_using) ---")
        ekey = {}
        for ei, e in enumerate(me.edges):
            ekey[(min(e.vertices), max(e.vertices))] = ei
        use = [0] * len(me.edges)
        for p in me.polygons:
            pv = list(p.vertices)
            k = len(pv)
            for i in range(k):
                a, b = pv[i], pv[(i + 1) % k]
                ei = ekey.get((min(a, b), max(a, b)))
                if ei is not None:
                    use[ei] += 1
        for ei, e in enumerate(me.edges):
            w("  e%-3d (%2d,%2d) used_by=%d" % (ei, e.vertices[0], e.vertices[1], use[ei]))
        w("")
        w("--- COMPONENT SUMMARY ---")
        for r in roots:
            ids = [i for i in range(n) if comp[i] == r]
            c = wco[ids]
            mn, mx = c.min(axis=0), c.max(axis=0)
            w("  c%-2d nverts=%2d faces=%2d worldmin(% .6f % .6f % .6f) worldmax(% .6f % .6f % .6f) dims(% .6f % .6f % .6f)" % (
                cid[r], len(ids), sum(1 for p in me.polygons if comp[p.vertices[0]] == r),
                mn[0], mn[1], mn[2], mx[0], mx[1], mx[2],
                mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]))
        # pairwise minimum vertex-to-vertex distance between components
        w("")
        w("  --- min vertex-to-vertex distance between components (m) ---")
        for i, ra in enumerate(roots):
            for rb in roots[i + 1:]:
                ia = [k for k in range(n) if comp[k] == ra]
                ib = [k for k in range(n) if comp[k] == rb]
                d = np.linalg.norm(wco[ia][:, None, :] - wco[ib][None, :, :], axis=2).min()
                w("    c%-2d - c%-2d : %.6f" % (cid[ra], cid[rb], d))
        w("")

    os.makedirs(os.path.dirname(A.out), exist_ok=True)
    with open(A.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("[a_dump_topology] wrote", A.out, len(lines), "lines")


main()
