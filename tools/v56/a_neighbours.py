"""a_neighbours.py -- offline: find scene objects near the wooden_boards* group.

Reads the compact world-AABB index produced by a_board_components.py and
reports every object whose AABB is within a given radius of a query point,
so the wall / ground support geometry can be identified without reopening
the 481 MB blend file.

Control-python only (no bpy).
"""

import argparse
import json
import math


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True)
    ap.add_argument("--query", required=True,
                    help="x,y,z in world units")
    ap.add_argument("--radius", type=float, default=2.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=400)
    A = ap.parse_args()

    q = [float(x) for x in A.query.split(",")]
    d = json.load(open(A.index, encoding="utf-8"))

    def aabb_dist(q, mn, mx):
        dd = 0.0
        for i in range(3):
            if q[i] < mn[i]:
                dd += (mn[i] - q[i]) ** 2
            elif q[i] > mx[i]:
                dd += (q[i] - mx[i]) ** 2
        return math.sqrt(dd)

    hits = []
    for o in d["objects"]:
        dist = aabb_dist(q, o["mn"], o["mx"])
        if dist <= A.radius:
            dims = [round(o["mx"][i] - o["mn"][i], 4) for i in range(3)]
            hits.append({
                "name": o["n"], "type": o["t"],
                "dist": round(dist, 4),
                "mn": o["mn"], "mx": o["mx"], "dims": dims,
                "nv": o.get("nv"), "nf": o.get("nf"),
                "mat": o.get("mat"),
            })
    hits.sort(key=lambda h: h["dist"])
    print("query %s radius %s -> %d objects" % (q, A.radius, len(hits)))
    for h in hits[:A.limit]:
        print("%8.3f %-9s %-42s dims=%-32s nv=%-6s mat=%s" % (
            h["dist"], h["type"], h["name"], str(h["dims"]), h["nv"], h["mat"]))
    if A.out:
        json.dump({"query": q, "radius": A.radius, "hits": hits},
                  open(A.out, "w", encoding="utf-8"), indent=1)
        print("wrote", A.out)


main()
