"""Build a NEW west-turn tail layout on the authored floor; never overwrite V6.4.

The candidate was selected from the native-floor and 0..90-degree swept-scenery
grid probes. This script performs fresh exact initial-contact checks before it
can write a candidate. A later independent full solve is still mandatory.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, "/data/raw/huzijian/project1_database/tools/v64")
import physics_common_r10 as pc

ROOT = Path("/data/raw/huzijian/project1_database")
ap = argparse.ArgumentParser()
ap.add_argument("--layout", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--report", required=True)
ap.add_argument("--variant", choices=("a", "b"), default="a")
args = ap.parse_args()
input_path, output_path, report_path = (Path(p).resolve() for p in (args.layout, args.out, args.report))
if any(ROOT not in p.parents for p in (input_path, output_path, report_path)):
    raise SystemExit("all paths must be project-scoped")
if output_path.exists() or report_path.exists():
    raise SystemExit("refuse to overwrite earlier layout or report")

# Local turn follows the existing second broad bend. F41-F43 and the rest of
# the approved double curve remain at their current author-facing positions.
# The centre-to-centre distances are 0.153, 0.141, 0.150, 0.100, 0.100 m.
PLACEMENTS_A = {
    "F44": (0.8000, 12.5000, 135.0),
    "F45": (0.7000, 12.6000, 180.0),
    "F46": (0.5500, 12.6000, 180.0),
    "F47": (0.4500, 12.6000, 180.0),
    "F48": (0.3500, 12.6000, 180.0),
}
PLACEMENTS_B = {
    "F44": (0.8000, 12.5000, 135.0),
    "F45": (0.7000, 12.6000, 180.0),
    "F46": (0.5500, 12.6000, 180.0),
    "F47": (0.4500, 12.7000, 135.0),
    "F48": (0.3900, 12.7900, 135.0),
}
PLACEMENTS = PLACEMENTS_A if args.variant == "a" else PLACEMENTS_B

layout = json.loads(input_path.read_text(encoding="utf-8"))
rows = {row["id"]: row for row in layout["objects"]}
if not set(PLACEMENTS) <= set(rows):
    raise SystemExit("missing tail objects")
manifest = json.loads(pc.DEFAULT_MANIFEST.read_text(encoding="utf-8"))
layout_new = copy.deepcopy(layout)
new_rows = {row["id"]: row for row in layout_new["objects"]}

with pc.World(hz=960, mode="upstream", verbose=False, layout_override=input_path) as world:
    floors = [sb for sb in world._static if world.body_names.get(sb) == "Floor_main"]
    if not floors:
        raise RuntimeError("authored floor absent")
    for sb in floors:
        world._P(pc.p.setCollisionFilterGroupMask, sb, -1, 8, -1)

    def support(x, y, yaw, T, W, H):
        Rz = Rotation.from_euler("z", yaw).as_matrix()
        zs = []
        for a in (-0.45, 0.0, 0.45):
            for b in (-0.45, 0.0, 0.45):
                px, py = np.array([x, y]) + (Rz @ np.array([a * T, b * W, 0.0]))[:2]
                hit = world._P(pc.p.rayTest, [float(px), float(py), 0.6],
                               [float(px), float(py), -0.6], collisionFilterMask=8)[0]
                if hit[0] not in floors:
                    raise RuntimeError(f"native-floor ray miss at {px:.4f},{py:.4f}")
                zs.append(float(hit[3][2]))
        if max(zs) - min(zs) > .001:
            raise RuntimeError(f"nonplanar native support at {x},{y}: {max(zs)-min(zs):.6f} m")
        return max(zs) + H / 2 + .0003, max(zs) - min(zs)

    edits = []
    for ident, (x, y, adeg) in PLACEMENTS.items():
        yaw = math.radians(adeg)
        T, W, H = (float(v) for v in manifest["objects"][ident]["dims_m"])
        z, floor_span = support(x, y, yaw, T, W, H)
        quat = Rotation.from_euler("z", yaw).as_quat().tolist()
        old = rows[ident]["settled_position"]
        for key in ("position", "settled_position"):
            new_rows[ident][key] = [x, y, z]
        for key in ("quaternion_xyzw", "settled_quaternion_xyzw"):
            new_rows[ident][key] = quat
        new_rows[ident]["yaw"] = yaw
        world.move_actor(ident, [x, y, z], quat)
        edits.append({"id": ident, "old_position": old, "new_position": [x, y, z],
                      "yaw_deg": adeg, "floor_height_span_m": floor_span})

    # Fresh geometry queries; the old contact manifold is not evidence for a
    # just-moved body. Every native obstacle remains present in this world.
    severe = []
    nearest_static = {}
    for ident in PLACEMENTS:
        body = world.actors[ident]
        nearby = []
        for sb in world._static:
            pts = world._P(pc.p.getClosestPoints, body, sb, .03)
            if not pts:
                continue
            depth = min(float(pt[8]) for pt in pts)
            name = world.body_names.get(sb, "unknown")
            nearby.append({"name": name, "distance_m": depth})
            if depth < -.001001:
                severe.append({"actor": ident, "other": name, "distance_m": depth})
        nearest_static[ident] = sorted(nearby, key=lambda v: v["distance_m"])[:5]
    pairs = []
    names = [f"F{i:02d}" for i in range(41, 49)]
    for first, second in zip(names, names[1:]):
        pts = world._P(pc.p.getClosestPoints, world.actors[first], world.actors[second], .4)
        distance = min(float(pt[8]) for pt in pts) if pts else None
        pairs.append({"pair": [first, second], "initial_gap_m": distance})
        if distance is not None and distance < -.001001:
            severe.append({"actor": first, "other": second, "distance_m": distance})
    for ident in PLACEMENTS:
        for other in world.actors:
            if other == ident or other in names:
                continue
            pts = world._P(pc.p.getClosestPoints, world.actors[ident], world.actors[other], .002)
            if pts:
                d = min(float(pt[8]) for pt in pts)
                if d < -.001001:
                    severe.append({"actor": ident, "other": other, "distance_m": d})
    if severe:
        raise RuntimeError("initial geometric overlap >1 mm: " + json.dumps(severe[:12]))

    for k in range(44, 49):
        prev = new_rows[f"F{k-1:02d}"]
        cur = new_rows[f"F{k:02d}"]
        a = np.asarray(prev["settled_position"][:2])
        b = np.asarray(cur["settled_position"][:2])
        cur["station_m"] = prev["station_m"] + float(np.linalg.norm(b - a))
    old_length = layout_new["route_length_m"]
    layout_new["route_length_m"] = new_rows["F48"]["station_m"]
    layout_new["status"] = "TAIL_WEST_CANDIDATE_PENDING_FULL_PHYSICS"
    layout_new["v65_tail_relayout"] = {
        "variant": args.variant,
        "source_layout": str(input_path), "scope": "F44..F48 on native floor; F41..F43 unchanged",
        "method": "native floor 9-point support plus sampled swept-scenery corridor",
        "original_route_length_m": old_length,
        "current_route_length_m": layout_new["route_length_m"],
        "route_samples_role": "historical approved reference; actor centreline is authoritative for F44..F48",
        "geometry_gate": "initial no >1 mm overlap; swept corridor is diagnostic until full solve",
        "original_author_scene_modified": False,
    }
    report = {"status": "INITIAL_GEOMETRY_PASS_FULL_SOLVE_PENDING", "variant": args.variant,
              "source_layout": str(input_path),
              "candidate_layout": str(output_path), "edits": edits, "tail_pairs": pairs,
              "nearest_static": nearest_static, "severe_initial_overlaps": severe,
              "old_length_m": old_length, "new_length_m": layout_new["route_length_m"]}

output_path.parent.mkdir(parents=True, exist_ok=True)
report_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open("x", encoding="utf-8") as handle:
    json.dump(layout_new, handle, indent=2, ensure_ascii=False)
with report_path.open("x", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, ensure_ascii=False)
print("CANDIDATE", output_path, flush=True)
print("REPORT", json.dumps({"status": report["status"], "new_length_m": report["new_length_m"],
                            "tail_pairs": pairs}, ensure_ascii=False), flush=True)
