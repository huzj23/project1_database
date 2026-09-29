"""V5.5 stage 05: diagnose why the box produced no contact with the bottle.

The first solve wrote `contacts.jsonl` with 0 bytes -- the box fell and nothing touched it. That
is a real failure and 05 section 4 says the response is to determine the cause, not to add a
force to the bottle.

Facts to check, all from the recorded trajectory rather than re-simulating:

  D1 where did the box actually go, and did it pass the bottle's height at all?
  D2 where was the bottle at each frame -- did it move at all?
  D3 what do the body AABBs say: do the box's swept x/y range and the bottle's x/y footprint
     actually intersect in the horizontal plane?
  D4 is the box resting on the tray rim, the table, or the lamp instead of reaching the bottle?
  D5 does the box's PATH pass over the bottle, i.e. is the horizontal offset correct in sign?

The design's offset is a DISTANCE from the bottle axis along +y, applied as
`axis + dvec * offset`. If the box was placed on the far side of the axis from where the strike
requires, the near face lies OUTSIDE the bottle silhouette and the box simply falls past it.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")
RUN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/20260929T030000"
DESIGN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/design.json"


def load_obj(path: Path):
    vs = []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                vs.append([float(p[1]), float(p[2]), float(p[3])])
    return np.asarray(vs, float)


def main() -> int:
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    traj = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))["bodies"]
    print("=" * 84)
    print("=== D1/D2: trajectories ===")
    for iid, rows in traj.items():
        p0 = np.array(rows[0]["position_m"])
        p1 = np.array(rows[-1]["position_m"])
        zs = [r["position_m"][2] for r in rows]
        print(f"  {iid:18s} start ({p0[0]:.4f},{p0[1]:.4f},{p0[2]:.4f}) "
              f"end ({p1[0]:.4f},{p1[1]:.4f},{p1[2]:.4f}) z range "
              f"{min(zs):.4f}..{max(zs):.4f}")

    box = traj["striker_box"]
    bot = traj["bottle_assembly"]
    print(f"\n  box z by frame (every 12th):")
    for r in box[::12]:
        print(f"    frame {r['frame']:3d} z={r['position_m'][2]:8.5f} "
              f"xy=({r['position_m'][0]:.4f},{r['position_m'][1]:.4f})")
    print(f"  bottle first/last pose:")
    for r in (bot[0], bot[-1]):
        print(f"    frame {r['frame']:3d} pos=({r['position_m'][0]:.4f},"
              f"{r['position_m'][1]:.4f},{r['position_m'][2]:.4f}) "
              f"q={[round(v,5) for v in r['quaternion_xyzw']]}")

    # ---- D3: horizontal overlap between the box's swept area and the bottle -----------
    print("\n=== D3: horizontal geometry ===")
    box_obj = RUN / "striker_box_collision.obj"
    bv = load_obj(box_obj)
    blocal = (bv.min(axis=0), bv.max(axis=0))
    print(f"  striker mesh local AABB {np.round(blocal[0],5)} .. {np.round(blocal[1],5)}")
    box_min, box_max = blocal
    # The box's world x/y AABB is its local AABB shifted by the recorded start position (no
    # rotation is applied at t=0, and the fall is vertical so x/y never change).
    bx = np.array(box[0]["position_m"])
    box_lo = np.array([bx[0] + box_min[0], bx[1] + box_min[1]])
    box_hi = np.array([bx[0] + box_max[0], bx[1] + box_max[1]])
    print(f"  box world x/y extent  x {box_lo[0]:.4f}..{box_hi[0]:.4f}  "
          f"y {box_lo[1]:.4f}..{box_hi[1]:.4f}")

    props = design["props"]
    b = props["bottle_assembly"]
    bmin, bmax = np.array(b["min"]), np.array(b["max"])
    axis = np.array(design["bottle_axis_xy"])
    print(f"  bottle x/y extent     x {bmin[0]:.4f}..{bmax[0]:.4f}  "
          f"y {bmin[1]:.4f}..{bmax[1]:.4f}")
    print(f"  bottle axis           ({axis[0]:.4f}, {axis[1]:.4f})")
    ov_x = min(box_hi[0], bmax[0]) - max(box_lo[0], bmin[0])
    ov_y = min(box_hi[1], bmax[1]) - max(box_lo[1], bmin[1])
    print(f"  horizontal overlap    x {ov_x*1000:+.3f} mm   y {ov_y*1000:+.3f} mm  "
          f"-> overlaps in both: {ov_x > 0 and ov_y > 0}")

    # ---- D4/D5: where the box stopped, and relative to what --------------------------
    print("\n=== D4/D5: where the box came to rest ===")
    bx_end = np.array(box[-1]["position_m"])
    z_end = bx_end[2]
    print(f"  box final z {z_end:.6f}; box mesh local z {box_min[2]:.6f}..{box_max[2]:.6f} "
          f"-> world bottom {z_end + box_min[2]:.6f}")
    layer = json.loads((ROOT / "outcomes/v55/scenes/italian_flat/layer_report.json")
                       .read_text(encoding="utf-8"))
    for nm, info in layer["static_collision"].items():
        print(f"    {nm:38s} top z {info['aabb_max'][2]:.6f}")
    print(f"  bottle top z {bmax[2]:.6f}")

    # ---- the design's own numbers, re-checked ----------------------------------------
    print("\n=== the design's strike, re-derived ===")
    strike = design["chosen"]
    print(f"  chosen: {strike['orientation']} direction {strike['direction']} "
          f"lever {strike['lever_arm_m']*1000:.1f} mm")
    print(f"  box centre start     {strike['box_centre_start']}")
    print(f"  centre offset        {strike['centre_offset_m']*1000:.3f} mm")
    print(f"  near face from axis  {strike['near_face_from_axis_m']*1000:.3f} mm")
    print(f"  radius at contact    {strike['radius_at_contact_m']*1000:.3f} mm")
    # The near face's signed position along the offset direction, relative to the axis.
    dvec = {"+y": (0.0, 1.0), "-y": (0.0, -1.0), "+x": (1.0, 0.0), "-x": (-1.0, 0.0)}[
        strike["direction"]]
    half_along = (abs(dvec[0]) * strike["half_x_m"] + abs(dvec[1]) * strike["half_y_m"])
    face_pos = strike["centre_offset_m"] - half_along
    print(f"  -> the box's NEAR face lies {face_pos*1000:+.3f} mm from the axis along "
          f"{strike['direction']}, i.e. {'outside' if abs(face_pos) > 0 else 'inside'} "
          f"the bottle by {abs(face_pos)*1000:.3f} mm")
    print(f"  -> the bottle's widest radius is {design['r_max_m']*1000:.3f} mm, so a near face at "
          f"{face_pos*1000:.3f} mm {'CLEARS' if abs(face_pos) > design['r_max_m'] else 'intersects'} "
          f"the silhouette")

    # Actual box centre start from the trajectory vs the design.
    print(f"\n  design centre start  {strike['box_centre_start']}")
    print(f"  actual centre start  {box[0]['position_m']}")
    dx = np.array(box[0]["position_m"]) - np.array(strike["box_centre_start"])
    print(f"  difference           {np.round(dx, 6)} m")

    out = {
        "box_start": box[0]["position_m"], "box_end": box[-1]["position_m"],
        "bottle_start": bot[0]["position_m"], "bottle_end": bot[-1]["position_m"],
        "box_world_xy": [box_lo.tolist(), box_hi.tolist()],
        "bottle_world_xy": [bmin[:2].tolist(), bmax[:2].tolist()],
        "overlap_xy_m": [float(ov_x), float(ov_y)],
        "overlaps_both_axes": bool(ov_x > 0 and ov_y > 0),
        "near_face_from_axis_m": float(face_pos),
        "bottle_max_radius_m": float(design["r_max_m"]),
        "near_face_clears_bottle": bool(abs(face_pos) > design["r_max_m"]),
        "box_resting_bottom_z": float(z_end + box_min[2]),
        "bottle_top_z": float(bmax[2]),
    }
    p = RUN / "diagnosis.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
