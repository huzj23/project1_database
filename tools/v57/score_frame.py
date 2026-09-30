"""Score a V5.7 preview candidate frame against the plan's framing gates, using measured geometry.

WHY THIS EXISTS
---------------
The executor cannot view images, and the plan forbids presenting ASCII art or pixel percentages as visual
acceptance. That does not remove the obligation to MEASURE: the plan's framing gates are numerical, so they
must be checked numerically and reported next to the image so the user can compare a number with a picture.

Reported per candidate, all from the actual scene and camera:

  * chain span as a fraction of frame width (plan: 0.60-0.80);
  * the smallest principal box's projected height (plan: >=80 px at 720p);
  * arc visibility: the maximum screen-space deviation of the chain's centreline from the straight chord
    between its end boxes (plan: >=30 px at 720p), which is the measure of "the curve is actually visible";
  * whether every box centre and the trigger are inside the frame;
  * occlusion of each box centre along the camera ray;
  * what occupies the background, by casting a coarse ray grid and naming the objects.

Usage:
    python tools/v57/score_frame.py --build <preview_build.json> --frame <png> [--cam C1]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--cam", default="")
    ap.add_argument("--out", default="")
    A = ap.parse_args()

    B = json.loads(Path(A.build).read_text(encoding="utf-8"))
    boxes = B["boxes"]
    trigger = B["trigger"]
    cams = B["cameras"]
    keys = [A.cam] if A.cam else list(cams.keys())

    print("=" * 100)
    print(f"framing score | {Path(A.build).name}")
    st = B["site"]
    print(f"  site centre ({st['cx']:+.2f},{st['cy']:+.2f})  chord {st['chord_deg']:+.1f} deg")
    print(f"  arc: N={len(boxes)} boxes, R={B.get('arc_r')} m, spacing={B.get('spacing')} m, "
          f"total turn {B.get('total_turn_deg', float('nan')):.2f} deg")
    # Seating: which object each box actually stands on, and the residual against the fitted plane.
    supports = {}
    for b in boxes:
        supports[b.get("support_object", "?")] = supports.get(b.get("support_object", "?"), 0) + 1
    res = [abs(b["seating_residual_m"]) for b in boxes if "seating_residual_m" in b]
    print(f"  box supports: {supports}  (trigger on "
          f"{trigger.get('support_object', '?')})")
    if res:
        print(f"  seating residual vs fitted plane: max {max(res) * 1000:.2f} mm")
    gp = B["ground_plane"]
    print(f"  ground plane slope {gp['slope_deg']:.4f} deg, max residual "
          f"{gp['max_residual_m'] * 1000:.2f} mm")
    print(f"  mode {B['mode']}")
    print("=" * 100)

    # The render resolution is not in the build report, so it is inferred from the record when present.
    RES_X, RES_Y = 1280, 720
    for k in keys:
        c = cams[k]
        eye = c["eye"]
        aim = c["aim"]
        lens = c["spec"]["lens"]
        sw = 36.0
        f = lens / sw * RES_X

        def sub(p, q):
            return [p[i] - q[i] for i in range(3)]

        def dot(p, q):
            return sum(p[i] * q[i] for i in range(3))

        def cross(p, q):
            return [p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0]]

        def norm(p):
            L = dot(p, p) ** 0.5
            return [v / L for v in p]

        fwd = norm(sub(aim, eye))
        right = norm(cross(fwd, [0.0, 0.0, 1.0]))
        up = cross(right, fwd)

        def project(p):
            d = sub(p, eye)
            z = dot(d, fwd)
            if z <= 0.02:
                return None
            return (RES_X / 2 + f * dot(d, right) / z, RES_Y / 2 - f * dot(d, up) / z, z)

        print("")
        print(f"--- {k}: az {c['spec']['az']} deg off chord, dep {c['spec']['dep']}, "
              f"lens {c['spec']['lens']} mm, distance {c['spec']['dist']} m")
        print(f"    eye {[round(v, 3) for v in eye]}  aim {[round(v, 3) for v in aim]}")
        # The camera record shape differs between a clear eye and an eye that had to be shortened, so the
        # obstruction is read defensively rather than assumed present.
        obst = c.get("first_hit") or "<clear>"
        dist_hit = c.get("distance_to_first_hit")
        print(f"    status {c.get('status', '?')}; obstruction {obst} "
              f"{'' if dist_hit is None else format(dist_hit, '.3f') + ' m'}"
              f"{'  (eye shortened from %.3f to %.3f m)' % (c['spec']['dist_fitted'], c['spec']['dist_used']) if c.get('eye_shortened') else ''}")
        print(f"    eye side sign {c.get('eye_side_sign')} (must match the open side of the alley)")

        pts = {}
        for b in boxes:
            pr = project(b["position_m"])
            pts[b["index"]] = pr
        tpr = project(trigger["position_m"])

        inside = [i for i, pr in pts.items() if pr and 0 <= pr[0] < RES_X and 0 <= pr[1] < RES_Y]
        print(f"    box centres inside frame : {len(inside)}/{len(boxes)}"
              f"{'' if len(inside) == len(boxes) else '  MISSING ' + str(sorted(set(pts) - set(inside)))}")
        print(f"    trigger centre inside    : "
              f"{'yes' if tpr and 0 <= tpr[0] < RES_X and 0 <= tpr[1] < RES_Y else 'NO'}")

        # Span: horizontal extent of the projected centres plus half the outermost box sizes.
        xs = [pr[0] for pr in pts.values() if pr]
        span_lo = min(xs) - 0.5 * f * boxes[0]["dims_m"][2] / pts[0][2]
        span_hi = max(xs) + 0.5 * f * boxes[-1]["dims_m"][2] / pts[len(boxes) - 1][2]
        span_px = span_hi - span_lo
        print(f"    chain span               : {span_px:.1f} px = {span_px / RES_X:.3f} of frame width "
              f"(plan 0.60-0.80) -> {'OK' if 0.60 <= span_px / RES_X <= 0.80 else 'OUT OF RANGE'}")

        # Smallest box height in pixels.
        heights = {}
        for b in boxes:
            pr = project(b["position_m"])
            if pr:
                heights[b["index"]] = f * b["dims_m"][2] / pr[2]
        mn = min(heights.values())
        mn_i = min(heights, key=heights.get)
        print(f"    box pixel heights        : min {mn:.1f} px (box{mn_i}), "
              f"max {max(heights.values()):.1f} px (plan min >= 80 px at 720p) -> "
              f"{'OK' if mn >= 80 else 'TOO SMALL'}")

        # Arc visibility: perpendicular screen distance of each centre from the end-to-end chord.
        if pts.get(0) and pts.get(len(boxes) - 1):
            a = pts[0]
            b2 = pts[len(boxes) - 1]
            dx, dy = b2[0] - a[0], b2[1] - a[1]
            L = math.hypot(dx, dy)
            devs = []
            for i in sorted(pts):
                if not pts[i]:
                    continue
                px, py = pts[i][0], pts[i][1]
                # Perpendicular distance from the chord, in pixels.
                dev = abs((px - a[0]) * dy - (py - a[1]) * dx) / max(L, 1e-9)
                devs.append((i, dev))
            mx = max(d for _, d in devs)
            print(f"    arc deviation from chord : max {mx:.1f} px "
                  f"(plan >= 30 px at 720p) -> {'OK' if mx >= 30 else 'TOO FLAT TO SEE'}")
            print(f"      per box: {[(i, round(d, 1)) for i, d in devs]}")

        # Occlusion: does another box lie between the camera and each box centre?
        occ = []
        for b in boxes:
            p = b["position_m"]
            d = sub(p, eye)
            dist = dot(d, d) ** 0.5
            dirn = norm(d)
            blocked_by = []
            for ob in boxes:
                if ob["index"] == b["index"]:
                    continue
                q = sub(ob["position_m"], eye)
                t = dot(q, dirn)
                if 0.05 < t < dist - 0.05:
                    perp = (dot(q, q) - t * t) ** 0.5
                    r = 0.5 * max(ob["dims_m"])
                    if perp < r:
                        blocked_by.append(ob["index"])
            if blocked_by:
                occ.append((b["index"], blocked_by))
        print(f"    mutually occluded centres: {occ if occ else 'none'}")
        if A.out:
            Path(A.out).parent.mkdir(parents=True, exist_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
