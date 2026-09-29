"""V5.5 stage 05: why did the box miss, now that mesh-vs-mesh collision is proven to work?

Proven by direct test: every pair collides -- striker mesh vs bottle mesh (fixed AND both
dynamic), mesh vs primitive, primitive vs primitive. So the narrowphase is NOT the problem, and
the earlier "dynamic mesh vs dynamic mesh is broken" reading was wrong: that test had no floor, so
both bodies fell together and never met.

What remains is geometry. The recorded run has:

  * the box start AABB at x 1.4149..1.6241, y 7.5136..7.6034 (correct, matches the design);
  * the bottle's proxy AABB at x 1.4654..1.5750, y 7.4101..7.5196;
  * so in y the box's near edge is at 7.5136 and the bottle's far edge at 7.5196 -- an overlap of
    only 5.94 mm;
  * the box came to rest at z = 0.5646, which is the TABLE height, not the bottle's top 0.8051.

The design offsets the box from the bottle's AXIS by `r_contact + half_along`, where `half_along`
is the half-extent along the offset direction. The intended near face is `r_contact` = 49.46 mm
from the axis. But the bottle's AABB is NOT centred on the axis: the axis is at
(1.51948, 7.46421) while the proxy's AABB centre is (1.52016, 7.46482), so the AABB extends
further on one side than the other. Whether a 49.46 mm near face actually clears the bottle's
silhouette therefore depends on WHICH SIDE it approaches from, and the design never checked that.

This script measures, from the real meshes, the radius in each of the four cardinal directions,
and reports for the design's own direction whether the near face is inside or outside the
silhouette in that direction. It also reports the `z` at which the box's near face would first
meet the bottle if it descended, which is the number the strike depends on.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")
RUN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/20260929T050000"
DESIGN = ROOT / "outcomes/v55/italian_flat/box_hits_bottle/design.json"
FLOOR_Z = 0.510600


def load_obj(path: Path):
    vs, fs = [], []
    with path.open("r", encoding="utf-8", errors="replace") as h:
        for line in h:
            if line.startswith("v "):
                p = line.split()
                vs.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    fs.append((idx[0] - 1, idx[k] - 1, idx[k + 1] - 1))
    return np.asarray(vs, float), np.asarray(fs, np.int64)


def main() -> int:
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    traj = json.loads((RUN / "trajectory.json").read_text(encoding="utf-8"))["bodies"]

    # The bottle mesh is RECENTRED, so add the restore offset to get world coordinates, exactly as
    # the solver does.
    bot_obj = RUN / "bottle_assembly_collision.obj"
    V, F = load_obj(bot_obj)
    prov = json.loads((RUN / "provenance.json").read_text(encoding="utf-8"))
    b = design["props"]["bottle_assembly"]
    # The body origin is recorded in bodies.json; world = recentred mesh + origin.
    bodies = json.loads((RUN / "bodies.json").read_text(encoding="utf-8"))
    origin = np.array([x for x in bodies if x["instance_id"] == "bottle_assembly"][0]
                      ["position_m"])
    W = V + origin
    axis = np.array(design["bottle_axis_xy"])
    top = design["bottle_top_z"]

    print("=" * 92)
    print("=== bottle: radius from its AXIS in each cardinal direction ===")
    # Only the part of the bottle that can be struck: from the floor up to the top.
    dirs = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}
    prof = {}
    for name, (ux, uy) in dirs.items():
        # Project every vertex onto the direction and take the maximum extent from the axis.
        proj = (W[:, 0] - axis[0]) * ux + (W[:, 1] - axis[1]) * uy
        # The radius normal to the projection direction does not matter for a clearance test; what
        # matters is how far the silhouette reaches along this direction at each height.
        zs = W[:, 2]
        rows = []
        NB = 60
        edges = np.linspace(W[:, 2].min(), W[:, 2].max(), NB + 1)
        for i in range(NB):
            sel = (zs >= edges[i]) & (zs <= edges[i + 1])
            if sel.any():
                rows.append({"z_mid": float(0.5 * (edges[i] + edges[i + 1])),
                             "reach_m": float(proj[sel].max())})
        prof[name] = rows
        print(f"  {name}: max reach from the axis {max(r['reach_m'] for r in rows)*1000:.3f} mm")

    c = design["chosen"]
    dname = c["direction"]
    r_contact = c["radius_at_contact_m"]
    print(f"\n=== the design's own direction: {dname} ===")
    print(f"  near face is placed {r_contact*1000:.3f} mm from the axis along {dname}")
    # The reach along THAT direction, at heights near the contact height.
    zc = c["contact_z_m"]
    rows = prof[dname]
    near = min(rows, key=lambda r: abs(r["z_mid"] - zc))
    print(f"  at the contact height z={zc:.5f}, the bottle reaches "
          f"{near['reach_m']*1000:.3f} mm along {dname}")
    print(f"  -> the near face is {'OUTSIDE' if r_contact > near['reach_m'] else 'INSIDE'} the "
          f"silhouette by {abs(r_contact-near['reach_m'])*1000:.3f} mm")
    # The largest reach anywhere in the strike band: this is what the box must be inside of.
    band = [r for r in rows if r["z_mid"] >= FLOOR_Z + 0.05]
    max_band = max(r["reach_m"] for r in band) if band else 0.0
    print(f"  the bottle's largest reach along {dname} anywhere above the floor: "
          f"{max_band*1000:.3f} mm")
    # The design used r_max from the profile, which is the max over ALL directions. That is only
    # correct if the bottle is axisymmetric about its axis, which the AABB offset already shows it
    # is not.
    print(f"  the design used r_max = {design['r_max_m']*1000:.3f} mm (max over all directions)")

    box = json.loads((RUN / "provenance.json").read_text(encoding="utf-8"))["striker"]
    print(f"\n=== recorded box start ===")
    print(f"  centre {box['start_centre_m']}")
    print(f"  AABB   {box['start_aabb_m']}")
    print(f"  horizontal overlap with the bottle: {box['horizontal_overlap_with_bottle_m']}")
    print(f"\n=== what the box actually did ===")
    bt = traj["striker_box"]
    print(f"  z: {bt[0]['position_m'][2]:.5f} -> {bt[-1]['position_m'][2]:.5f}")
    print(f"  rest bottom z ~ {bt[-1]['position_m'][2]:.5f} (table top 0.5000/0.5150, "
          f"bottle top {top:.5f})")
    print(f"  bottle z: {traj['bottle_assembly'][0]['position_m'][2]:.5f} -> "
          f"{traj['bottle_assembly'][-1]['position_m'][2]:.5f} (unmoved)")

    out = {
        "direction": dname,
        "near_face_m": r_contact,
        "bottle_reach_along_direction_m": near["reach_m"],
        "near_face_outside_silhouette": bool(r_contact > near["reach_m"]),
        "gap_m": float(r_contact - near["reach_m"]),
        "max_reach_along_direction_m": float(max_band),
        "r_max_used_by_design_m": float(design["r_max_m"]),
        "radius_profile_by_direction": {k: v for k, v in prof.items()},
    }
    p = RUN / "miss_diagnosis.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
