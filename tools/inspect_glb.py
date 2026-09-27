"""Inspect a GLB's structure without Blender: node hierarchy, transforms, scale.

We need to know *why* Kubric's glTF path throws the ReplicaCAD stage hundreds of
metres away.  Kubric forces `rotation_quaternion=(0.707,-0.707,0,0)` and applies
rotation only (not location/scale), so any root transform in the file survives
and can be mangled.
"""

from __future__ import annotations

import json
import struct
import sys


def read_glb(path: str):
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))
        assert magic == 0x46546C67, "not a GLB"
        chunks = {}
        while f.tell() < length:
            clen, ctype = struct.unpack("<II", f.read(8))
            data = f.read(clen)
            chunks[ctype] = data
    js = json.loads(chunks[0x4E4F534A].decode("utf-8"))
    return js, chunks


def mat_summary(m):
    """Human-readable summary of a glTF node transform."""
    if m is None:
        return "identity"
    if "matrix" in m:
        v = m["matrix"]
        return (f"matrix t=({v[12]:.3f},{v[13]:.3f},{v[14]:.3f}) "
                f"sx={v[0]:.4f} sy={v[5]:.4f} sz={v[10]:.4f}")
    t = m.get("translation", [0, 0, 0])
    r = m.get("rotation", [0, 0, 0, 1])
    s = m.get("scale", [1, 1, 1])
    return f"TRS t=({t[0]:.3f},{t[1]:.3f},{t[2]:.3f}) r={[round(x,3) for x in r]} s={[round(x,4) for x in s]}"


def main(paths):
    for path in paths:
        js, chunks = read_glb(path)
        print(f"===== {path.split('/')[-1]} =====")
        print(f"  asset      : {js.get('asset')}")
        print(f"  scenes     : {len(js.get('scenes', []))}  "
              f"default={js.get('scene')}")
        print(f"  nodes      : {len(js.get('nodes', []))}")
        print(f"  meshes     : {len(js.get('meshes', []))}")
        print(f"  materials  : {len(js.get('materials', []))}")
        print(f"  images     : {len(js.get('images', []))}")
        print(f"  extensions : {js.get('extensionsUsed')}")

        nodes = js.get("nodes", [])
        scene = js.get("scenes", [{}])[js.get("scene", 0)]
        roots = scene.get("nodes", [])
        print(f"  root nodes : {roots}")

        # walk the tree from the roots, printing transforms
        def walk(idx, depth, acc_t, acc_s):
            n = nodes[idx]
            m = n.get("matrix")
            t = n.get("translation", [0, 0, 0])
            s = n.get("scale", [1, 1, 1])
            if m:
                t = [m[12], m[13], m[14]]
                s = [m[0], m[5], m[10]]
            nt = [acc_t[i] + t[i] * acc_s[i] for i in range(3)]
            ns = [acc_s[i] * s[i] for i in range(3)]
            name = n.get("name", f"node{idx}")
            kind = "MESH" if "mesh" in n else ("cam" if "camera" in n else "grp")
            if depth <= 3 or "mesh" in n:
                print(f"    {'  '*depth}[{kind}] {name[:40]:40s} {mat_summary(m)}")
                if "mesh" in n and depth > 0:
                    print(f"    {'  '*depth}    -> accumulated t={[round(x,2) for x in nt]} "
                          f"s={[round(x,4) for x in ns]}")
            for c in n.get("children", []):
                walk(c, depth + 1, nt, ns)

        for r in roots:
            walk(r, 1, [0, 0, 0], [1, 1, 1])
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
