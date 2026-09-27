"""Print the raw glTF node transforms for a ReplicaCAD stage, and compute the
world-space extent the file *intends*.

The earlier summary mislabelled TRS nodes as 'identity' because it only looked at
the 'matrix' key, so we re-read the raw dicts here.
"""

from __future__ import annotations

import json
import struct
import sys


def read_glb(path):
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))
        chunks = {}
        while f.tell() < length:
            clen, ctype = struct.unpack("<II", f.read(8))
            chunks[ctype] = f.read(clen)
    return json.loads(chunks[0x4E4F534A].decode("utf-8"))


def main(path):
    js = read_glb(path)
    nodes = js["nodes"]
    print(f"===== {path.split('/')[-1]} =====")
    print(f"  nodes={len(nodes)} meshes={len(js['meshes'])} "
          f"materials={len(js.get('materials', []))} images={len(js.get('images', []))}")
    print()
    print("  raw node transforms:")
    for i, n in enumerate(nodes):
        keys = [k for k in ("matrix", "translation", "rotation", "scale") if k in n]
        summary = {k: n[k] for k in keys}
        kind = "MESH" if "mesh" in n else ("EMPTY" if "children" in n else "?")
        nm = n.get("name", f"node{i}")
        print(f"    [{i:2d}] {kind:5s} {nm[:34]:34s} children={n.get('children', [])}")
        if summary:
            for k, v in summary.items():
                if isinstance(v, list) and len(v) > 4:
                    print(f"           {k}: t=({v[12]:.3f},{v[13]:.3f},{v[14]:.3f})"
                          f" s=({v[0]:.5f},{v[5]:.5f},{v[10]:.5f})")
                else:
                    print(f"           {k}: {[round(x,5) for x in v] if isinstance(v,list) else v}")

    # accumulate the world scale down the tree
    print()
    print("  accumulated world transform of mesh nodes:")
    scene = js["scenes"][js.get("scene", 0)]

    def walk(idx, t, s, depth):
        n = nodes[idx]
        if "matrix" in n:
            m = n["matrix"]
            nt = [m[12], m[13], m[14]]
            ns = [m[0], m[5], m[10]]
        else:
            nt = n.get("translation", [0, 0, 0])
            ns = n.get("scale", [1, 1, 1])
        T = [t[i] + nt[i] * s[i] for i in range(3)]
        S = [s[i] * ns[i] for i in range(3)]
        if "mesh" in n:
            print(f"    {n.get('name','?')[:36]:36s} t=({T[0]:7.3f},{T[1]:7.3f},{T[2]:7.3f}) "
                  f"s=({S[0]:.5f},{S[1]:.5f},{S[2]:.5f})")
        for c in n.get("children", []):
            walk(c, T, S, depth + 1)

    for r in scene.get("nodes", []):
        walk(r, [0, 0, 0], [1, 1, 1], 0)


if __name__ == "__main__":
    main(sys.argv[1])
