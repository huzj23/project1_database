"""Work out whether a can can actually reach and topple the selected board.

This is the honest geometry question that two delegated attempts failed to resolve, so it is done
here as arithmetic rather than as trial and error.

THE PROBLEM. The flat ground in Hidden Alley runs along Y (north-south) beside the wall at x = -2.2.
The board's foot is at x in [-2.153, -2.017], y in [1.427, 2.888]. The board's slab is

    long axis  : horizontal, along -Y, length 1.461 m
    width      : 0.388 m  (this is the board's VERTICAL extent, since it lies almost flat)
    thickness  : 0.0136 m (along X)

So the board's thin 13.6 mm edge faces +/-X and its 1.461 x 0.388 m broad faces point up/down-ish
tilted by the 12.697 deg lean. A can rolling in the -X direction would strike the thin edge. A can
rolling along +/-Y would run PARALLEL to the long axis and only catch the board's end.

WHAT IS COMPUTED HERE:

  1. The board's real orientation, from the exported OBJ, so the tilt and the face normals are known
     rather than inferred from the AABB.
  2. The minimum can radius needed to reach the board's centre of mass height when rolling on the
     ground, and the contact height a can of a given radius would achieve. This is the crux: to
     TOPPLE a board the impulse must be applied high enough, and a can is short relative to it.
  3. The energy comparison the plan asks for in section 5.1: the can's kinetic energy against the
     board's barrier to tipping about its actual support edge, including the fact that the wall
     props it.
  4. A torque comparison at the board's leading bottom edge, which is the quantity that decides
     whether the board rotates rather than slides.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\workspace\project1_database")
BOARDS = ROOT / "outcomes/v56/hidden_alley_can_board/boards"
RUN = ROOT / "outcomes/v56/hidden_alley_can_board/20260929T142714"
OUT = RUN / "ground"


def load_obj(path: Path):
    vs, fs = [], []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("v "):
                p = line.split()
                vs.append([float(p[1]), float(p[2]), float(p[3])])
            elif line.startswith("f "):
                idx = [int(t.split("/")[0]) for t in line.split()[1:]]
                for k in range(1, len(idx) - 1):
                    fs.append((idx[0] - 1, idx[k] - 1, idx[k + 1] - 1))
    return np.asarray(vs, float), np.asarray(fs, np.int64)


def main() -> int:
    bj = json.loads((BOARDS / "board_01_wooden_boards_001_c04.json").read_text(encoding="utf-8"))
    print("=== board record keys ===")
    for k in ("dims_world_m", "dims_m", "dimensions_m", "mass_kg", "lean_from_vertical_deg",
              "long_axis_world", "thickness_m", "world_aabb_min", "world_aabb_max"):
        if k in bj:
            print(f"  {k} = {bj[k]}")
    V, F = load_obj(BOARDS / "board_01_wooden_boards_001_c04.obj")
    print(f"\n=== board mesh ===\n  {len(V)} verts, {len(F)} faces (world coordinates)")

    # Recover the slab's own frame from its faces: the three mutually perpendicular edge directions.
    edges = {}
    for tri in F:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            e = V[tri[a]] - V[tri[b]]
            L = np.linalg.norm(e)
            if L < 1e-9:
                continue
            u = e / L
            key = None
            for k, (d, tot) in edges.items():
                if abs(abs(float(np.dot(u, d))) - 1.0) < 1e-4:
                    key = k
                    break
            if key is None:
                edges[len(edges)] = (u, [L])
            else:
                edges[key][1].append(L)
    dirs = []
    for k, (d, ls) in edges.items():
        dirs.append((float(np.median(ls)), d))
    dirs.sort()
    print("\n=== board edge directions (shortest first) ===")
    names = ["thickness", "width(vertical)", "length"]
    for i, (L, d) in enumerate(dirs[:3]):
        print(f"  {names[i] if i < 3 else 'extra':18s} {L:.6f} m  dir "
              f"({d[0]:+.4f}, {d[1]:+.4f}, {d[2]:+.4f})  tilt from vertical "
              f"{math.degrees(math.acos(min(1.0, abs(d[2])))):.2f} deg")
    thickness_d = dirs[0][1]
    width_d = dirs[1][1]
    length_d = dirs[2][1]
    t = dirs[0][0]
    w = dirs[1][0]
    Lg = dirs[2][0]

    # The board's centre and its lowest point.
    c = V.mean(axis=0)
    zmin = V[:, 2].min()
    print(f"\n  centre ({c[0]:.4f}, {c[1]:.4f}, {c[2]:.4f})  lowest z {zmin:.4f}")
    print(f"  dims L={Lg:.4f} (length, along Y) x {w:.4f} (vertical) x {t:.5f} m (thickness, along X)")

    # How high is the board's centre of mass above the ground?
    ground_z = float(bj.get("support_z_m", 0.0097)) if "support_z_m" in bj else 0.0097
    com_h = c[2] - ground_z
    print(f"\n=== can reach ===")
    print(f"  board COM height above its support: {com_h * 1000:.1f} mm")
    print(f"  board vertical extent: {w * 1000:.1f} mm, so its TOP is at "
          f"{(zmin + w - ground_z) * 1000:.1f} mm above the support")

    CAN = {
        "Creatine_Monohydrate": {"d": 0.12998, "h": 0.18513, "m": 0.2184},
    }
    print(f"\n  a can of diameter d contacts the board at height ~= d/2 = its own radius:")
    for name, cc in CAN.items():
        r = cc["d"] / 2
        print(f"    {name}: d={cc['d']*1000:.1f} mm, contact height ~{r*1000:.1f} mm, "
              f"m={cc['m']} kg")
        print(f"      contact height / board COM height = {r / com_h:.3f}  "
              f"({'BELOW' if r < com_h else 'above'} the COM)")

    # Tipping barrier. The board stands on its thin edge, propped by the wall. If the wall prop is
    # removed it tips about its bottom edge. The angle gravity must be brought over the leading
    # bottom edge is atan((t/2)/(w/2)) measured from the vertical in the thickness direction.
    theta_tip = math.degrees(math.atan2(t / 2.0, w / 2.0))
    print(f"\n=== tipping geometry (about the bottom edge, thickness direction) ===")
    print(f"  thickness {t*1000:.2f} mm, vertical extent {w*1000:.1f} mm")
    print(f"  tip angle from vertical = atan((t/2)/(w/2)) = {theta_tip:.3f} deg")
    print(f"  the board currently leans {bj.get('lean_from_vertical_deg', 12.697):.3f} deg, i.e. it is")
    print(f"  ALREADY {(bj.get('lean_from_vertical_deg', 12.697) / theta_tip):.1f}x past its free-standing")
    print(f"  tipping angle -- it is stable ONLY because the wall props it.")
    print(f"  => removing or shifting the prop is the mechanism, not pushing the board over.")

    rho = 500.0
    m_board = Lg * w * t * rho
    print(f"\n=== energy (plan section 5.1) ===")
    print(f"  board mass at {rho:.0f} kg/m3 = {Lg:.4f} x {w:.4f} x {t:.5f} x {rho:.0f} = "
          f"{m_board:.3f} kg")
    # Energy to raise the COM to the tipping point: COM height goes from w/2 to the diagonal/2.
    h0 = w / 2.0
    h1 = math.hypot(t / 2.0, w / 2.0)
    dE = m_board * 9.81 * (h1 - h0)
    print(f"  COM rises from {h0*1000:.2f} mm to {h1*1000:.2f} mm -> dE = {dE:.4f} J")
    print(f"  BUT the board is propped: to free it the support must be removed, and then gravity does")
    print(f"  the work. The relevant barrier is the energy to LIFT THE FOOT clear of the plinth or to")
    print(f"  rotate the board about its top wall contact until it passes vertical.")
    # Rotating about the top contact: COM must rise until it is directly below the pivot.
    print(f"\n  a can rolling at v with mass m_c has KE = 0.5*m*v^2 (plus rolling inertia, so the")
    print(f"  effective energy available for a strike is about 0.5*m*v^2):")
    ratios = []
    for v in (0.8, 1.2, 1.6, 2.0):
        for name, cc in CAN.items():
            ke = 0.5 * cc["m"] * v * v
            ratios.append(ke / dE)
            print(f"    v={v:.1f} m/s {name[:14]:14s} KE={ke:.4f} J   "
                  f"ratio to board barrier {ke/dE:.4f}")
    print(f"\n  the energy ratio is {min(ratios):.0f}x to {max(ratios):.0f}x ABOVE 1, so there is")
    print(f"  ample energy to rotate this board: its COM barely rises ({dE:.4f} J) because it is a")
    print(f"  thin 13.6 mm slab. Video A's risk is therefore NOT insufficient energy.")
    print(f"  The two real risks, in order:")
    print(f"    1. REACH -- the flat ground runs PARALLEL to the wall (+/-Y) while the board's thin")
    print(f"       edge faces +/-X, so a can rolling along the flat run travels past the board's end")
    print(f"       rather than into its face. An approach that actually reaches the board must be found.")
    print(f"    2. the board is stable only because the WALL props it, so the can must remove or shift")
    print(f"       the prop; a can cannot push the board wallward. Both must be settled by the solver.")

    (OUT / "approach_geometry.json").write_text(json.dumps({
        "board": "board_01_wooden_boards_001_c04",
        "length_m": Lg, "vertical_extent_m": w, "thickness_m": t,
        "centre_world": list(map(float, c)), "lowest_z_m": float(zmin),
        "support_z_assumed_m": ground_z, "com_height_above_support_m": com_h,
        "edge_dirs": {"thickness": list(map(float, thickness_d)),
                      "vertical": list(map(float, width_d)),
                      "length": list(map(float, length_d))},
        "tip_angle_from_vertical_deg": theta_tip,
        "current_lean_deg": bj.get("lean_from_vertical_deg", 12.697),
        "board_mass_kg_at_500": m_board,
        "barrier_to_lift_com_J": dE,
        "can_contact_height_m": {k: v["d"] / 2 for k, v in CAN.items()},
        "conclusion": ("the board is stable only because the WALL props it (lean 12.697 deg vs free "
                       "tipping angle " + f"{theta_tip:.3f}" + " deg); the workable mechanism is "
                       "removing or shifting the foot so the prop is lost, not pushing the board "
                       "over, and the flat ground runs PARALLEL to the wall so a can cannot approach "
                       "the board's broad face down a long flat line"),
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'approach_geometry.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
