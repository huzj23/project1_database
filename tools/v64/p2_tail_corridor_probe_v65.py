"""Read-only diagnostic: map native-floor support and swept scenery clearance.

Each sampled actor is moved only inside this throwaway PyBullet world. The
author scene, layout JSON, and all previously recorded outcomes are untouched.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/data/raw/huzijian/project1_database/tools/v64")
import physics_common_r10 as pc

ROOT = Path("/data/raw/huzijian/project1_database")
ap = argparse.ArgumentParser()
ap.add_argument("--layout", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--x-min", type=float, default=0.70)
ap.add_argument("--x-max", type=float, default=1.70)
ap.add_argument("--y-min", type=float, default=12.10)
ap.add_argument("--y-max", type=float, default=12.60)
ap.add_argument("--step", type=float, default=0.10)
ap.add_argument("--angles", default="0,45,90,135,180")
ap.add_argument("--pieces", default="F42,F44,F45,F47")
args = ap.parse_args()
layout_path = Path(args.layout).resolve()
out_path = Path(args.out).resolve()
if ROOT not in layout_path.parents or ROOT not in out_path.parents:
    raise SystemExit("all input and output paths must stay inside the project")
if out_path.exists():
    raise SystemExit("refuse output overwrite")
out_path.parent.mkdir(parents=True, exist_ok=True)
manifest = json.loads(pc.DEFAULT_MANIFEST.read_text())
pieces = args.pieces.split(",")
angles = [int(x) for x in args.angles.split(",")]
if not set(pieces) <= {"F42", "F43", "F44", "F45", "F46", "F47", "F48"}:
    raise SystemExit("probe only the existing tail")
if args.step <= 0 or args.step > 0.2:
    raise SystemExit("invalid grid step")


def rot_axis(axis, angle):
    axis = np.asarray(axis, float)
    axis /= np.linalg.norm(axis)
    x, y, z = axis
    K = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]], float)
    return np.eye(3) + math.sin(angle) * K + (1 - math.cos(angle)) * (K @ K)


def quat_from_matrix(R):
    from scipy.spatial.transform import Rotation
    return Rotation.from_matrix(R).as_quat().tolist()


with pc.World(hz=960, mode="upstream", verbose=False, layout_override=layout_path) as world:
    floors = [body for body in world._static if world.body_names.get(body) == "Floor_main"]
    if not floors:
        raise RuntimeError("native floor missing")
    for body in floors:
        world._P(pc.p.setCollisionFilterGroupMask, body, -1, 8, -1)
    statics = []
    for body in world._static:
        name = world.body_names[body]
        if name == "Floor_main":
            continue
        lo, hi = world._P(pc.p.getAABB, body)
        statics.append((body, name, np.asarray(lo), np.asarray(hi)))
    print("FLOOR_CHUNKS", len(floors), "NONFLOOR_CHUNKS", len(statics), flush=True)

    def support(x, y, yaw, T, W, H):
        R = rot_axis((0, 0, 1), yaw)
        zs = []
        for a in (-0.45, 0, 0.45):
            for b in (-0.45, 0, 0.45):
                px, py = np.array([x, y]) + (R @ np.array([a * T, b * W, 0]))[:2]
                hit = world._P(pc.p.rayTest, [float(px), float(py), 0.6],
                               [float(px), float(py), -0.6], collisionFilterMask=8)[0]
                if hit[0] not in floors:
                    return None, "floor_miss"
                zs.append(hit[3][2])
        span = max(zs) - min(zs)
        if span > 0.001:
            return None, "uneven_floor"
        return max(zs) + H / 2 + 0.0003, None

    result = {"source_layout": str(layout_path), "method": "actual native floor ray + 0..90 degree pivot sweep",
              "x_grid": [args.x_min, args.x_max, args.step],
              "y_grid": [args.y_min, args.y_max, args.step], "angles_deg": angles, "pieces": {}}
    for ident in pieces:
        body = world.actors[ident]
        rec = manifest["objects"][ident]
        T, W, H = (float(n) for n in rec["dims_m"])
        piece_rows = []
        refusals = {}
        old = next(row for row in world.layout["objects"] if row["id"] == ident)
        for adeg in angles:
            yaw = math.radians(adeg)
            direction = np.array([math.cos(yaw), math.sin(yaw), 0.])
            pivot_axis = np.cross(np.array([0., 0., 1.]), direction)
            R0 = rot_axis((0, 0, 1), yaw)
            q0 = quat_from_matrix(R0)
            for x in np.arange(args.x_min, args.x_max + 1e-9, args.step):
                for y in np.arange(args.y_min, args.y_max + 1e-9, args.step):
                    z, reason = support(float(x), float(y), yaw, T, W, H)
                    if reason:
                        refusals[reason] = refusals.get(reason, 0) + 1
                        continue
                    centre0 = np.array([x, y, z])
                    world.move_actor(ident, centre0, q0)
                    reach = T + W + H + 0.03
                    near = [(sb, name) for sb, name, lo, hi in statics
                            if lo[0] - reach <= x <= hi[0] + reach
                            and lo[1] - reach <= y <= hi[1] + reach]
                    minimum = (0.12, "none", None)
                    leading_edge = centre0 + R0 @ np.array([T / 2, 0., -H / 2])
                    for theta in range(0, 91, 10):
                        Rr = rot_axis(pivot_axis, math.radians(theta))
                        centre = leading_edge + Rr @ (centre0 - leading_edge)
                        world.move_actor(ident, centre, quat_from_matrix(Rr @ R0))
                        for sb, name in near:
                            hits = world._P(pc.p.getClosestPoints, body, sb, 0.12)
                            if hits:
                                nearest = float(min(pt[8] for pt in hits))
                                if nearest < minimum[0]:
                                    minimum = (nearest, name, theta)
                    if minimum[0] < 0.005:
                        refusals["sweep_blocked"] = refusals.get("sweep_blocked", 0) + 1
                        continue
                    piece_rows.append({"x": round(float(x), 4), "y": round(float(y), 4),
                                       "z": round(float(z), 5), "yaw_deg": adeg,
                                       "swept_clearance_m": round(minimum[0], 5),
                                       "closest_static": minimum[1], "closest_at_deg": minimum[2],
                                       "old_xy_distance_m": round(float(np.hypot(x - old["settled_position"][0],
                                                                              y - old["settled_position"][1])), 4)})
        piece_rows.sort(key=lambda row: row["old_xy_distance_m"])
        result["pieces"][ident] = {"tested": len(angles) *
                                     len(np.arange(args.x_min, args.x_max + 1e-9, args.step)) *
                                     len(np.arange(args.y_min, args.y_max + 1e-9, args.step)),
                                     "refusals": refusals, "safe": piece_rows}
        print("PIECE", ident, "SAFE", len(piece_rows), "REFUSALS", refusals, flush=True)
        for row in piece_rows[:8]:
            print(" ", row, flush=True)

with out_path.open("x", encoding="utf-8") as handle:
    json.dump(result, handle, indent=2, ensure_ascii=False)
print("OUTPUT", out_path, flush=True)
