"""Which board presents a face to a flat lane, and where does a can actually hit it?

`a3_reach_geometry` established that the alley floor is flat along Y and dished along X, so a can can
only roll a genuinely flat long path along Y. The board chosen for its physics (c4) is a slab lying
almost flat whose thin edge faces X, so a Y-travelling can passes it. This script checks all four
exported boards and answers, per board, the question that actually decides video A:

  **does a can rolling along a flat Y lane strike this board's face, and at what height?**

For each board it recovers the slab's own frame from the OBJ's face normals, then computes:
  * which of the slab's three axes is nearest to the can's travel direction (X or Y);
  * the projected area the board presents to that direction, which is the target the can must hit;
  * the height of the board's COM above the ground, versus the height a can of a given radius can
    strike at, which decides whether the strike can topple rather than merely slide it;
  * the free-standing tipping angle, against the board's actual lean -- the quantity that says whether
    the board is intrinsically stable or is standing only because the wall props it.

The last two are the decisive ones and neither is visible in a bounding box.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\workspace\project1_database")
BOARDS = ROOT / "outcomes/v56/hidden_alley_can_board/boards"
OUT = ROOT / "outcomes/v56/hidden_alley_can_board/20260929T142714/ground"

CAN_D = 0.12998
CAN_M = 0.2184
FLOOR_Z = -0.040


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


def slab_frame(V, F):
    """The slab's three edge directions and lengths, clustered from its own edges."""
    fams = []
    for tri in F:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            e = V[tri[a]] - V[tri[b]]
            L = float(np.linalg.norm(e))
            if L < 1e-9:
                continue
            u = e / L
            for f in fams:
                if abs(abs(float(np.dot(u, f["d"]))) - 1.0) < 1e-4:
                    f["ls"].append(L)
                    break
            else:
                fams.append({"d": u, "ls": [L]})
    out = [{"len": float(np.median(f["ls"])), "dir": f["d"]} for f in fams]
    out.sort(key=lambda x: x["len"])
    return out


def main() -> int:
    files = sorted(BOARDS.glob("board_0*_*.obj"))
    print("=" * 104)
    print("board presentation analysis -- does a can on a flat Y lane strike this board's face?")
    print(f"  can: diameter {CAN_D*1000:.1f} mm, mass {CAN_M} kg, strike height ~= radius "
          f"{CAN_D/2*1000:.1f} mm")
    print(f"  floor top z = {FLOOR_Z:+.3f} m; the flat lanes run along Y\n")

    rows = []
    for p in files:
        V, F = load_obj(p)
        s = slab_frame(V, F)
        if len(s) < 3:
            print(f"  {p.name}: only {len(s)} distinct edge families; skipped")
            continue
        t, w, L = s[0], s[1], s[2]
        c = V.mean(axis=0)
        zmin = float(V[:, 2].min())
        # Which axis is most nearly parallel to X (the wall normal) and to Y (the flat lane)?
        def align(d, axis):
            return abs(float(np.dot(d / np.linalg.norm(d), np.array(axis, float))))
        faces = {"X": align(t["dir"], (1, 0, 0)), "Y": align(t["dir"], (0, 1, 0))}
        # A slab blocks travel along the axis of its THICKNESS. So the can must travel along the
        # thickness axis to strike a face; travelling along the length or width axis grazes past.
        travel_axis = "X" if faces["X"] > faces["Y"] else "Y"
        # The area presented to travel along the thickness axis:
        present = w["len"] * L["len"]
        # Tipping: rotating about the bottom edge in the thickness direction.
        tip_deg = math.degrees(math.atan2(t["len"] / 2.0, w["len"] / 2.0))
        com_h = float(c[2] - zmin)
        # Which floor z applies under this board? Use the actual minimum.
        mass = L["len"] * w["len"] * t["len"] * 500.0
        dE = mass * 9.81 * (math.hypot(t["len"] / 2, w["len"] / 2) - w["len"] / 2)
        ke = 0.5 * CAN_M * 1.2 ** 2
        rows.append({
            "file": p.name, "thickness_m": t["len"], "width_m": w["len"], "length_m": L["len"],
            "thickness_dir": list(map(float, t["dir"])),
            "centre": list(map(float, c)), "lowest_z": zmin, "com_height_m": com_h,
            "presented_area_m2": present, "travel_axis_for_face_strike": travel_axis,
            "tip_angle_deg": tip_deg, "mass_kg_at_500": mass,
            "barrier_J": dE, "can_ke_at_1p2_J": ke, "energy_ratio": ke / dE,
            "strike_height_over_com": (CAN_D / 2) / com_h,
        })

    print(f"  {'board':34s} {'thick_mm':>9s} {'w_mm':>8s} {'L_mm':>8s} {'face':>5s} "
          f"{'area_m2':>8s} {'tip_deg':>8s} {'COM_mm':>7s} {'mass_kg':>8s} {'strike/COM':>10s}")
    for r in rows:
        print(f"  {r['file']:34s} {r['thickness_m']*1000:9.2f} {r['width_m']*1000:8.1f} "
              f"{r['length_m']*1000:8.1f} {r['travel_axis_for_face_strike']:>5s} "
              f"{r['presented_area_m2']:8.4f} {r['tip_angle_deg']:8.3f} "
              f"{r['com_height_m']*1000:7.1f} {r['mass_kg_at_500']:8.3f} "
              f"{r['strike_height_over_com']:10.3f}")

    print("\n=== interpretation ===")
    for r in rows:
        print(f"\n  {r['file']}")
        print(f"    thickness {r['thickness_m']*1000:.2f} mm -> a can must travel along "
              f"{r['travel_axis_for_face_strike']} to strike a FACE")
        print(f"    the flat lanes run along Y, so this board is "
              f"{'REACHABLE face-on from a flat lane' if r['travel_axis_for_face_strike'] == 'Y' else 'NOT reachable face-on from a flat Y lane (a Y-travelling can grazes its end)'}")
        print(f"    free-standing tip angle {r['tip_angle_deg']:.3f} deg; strike height is "
              f"{r['strike_height_over_com']*100:.0f}% of its COM height")
        print(f"    barrier {r['barrier_J']:.4f} J vs can KE {r['can_ke_at_1p2_J']:.4f} J at 1.2 m/s "
              f"-> ratio {r['energy_ratio']:.1f}x")

    reach = [r for r in rows if r["travel_axis_for_face_strike"] == "Y"]
    print(f"\n=== VERDICT ===")
    if reach:
        best = max(reach, key=lambda r: r["presented_area_m2"])
        print(f"  {len(reach)} of {len(rows)} boards can be struck face-on from a flat Y lane.")
        print(f"  largest presented face: {best['file']} at {best['presented_area_m2']:.4f} m2")
        print(f"    tip angle {best['tip_angle_deg']:.3f} deg, COM {best['com_height_m']*1000:.1f} mm, "
              f"mass {best['mass_kg_at_500']:.3f} kg")
        print(f"  a can strikes at ~{CAN_D/2*1000:.0f} mm, which is "
              f"{best['strike_height_over_com']*100:.0f}% of this board's COM height")
    else:
        print("  NO board presents a face to the flat Y lane. Options: rotate a board within its")
        print("  original region (permitted by 5.1.2 with a record), or use an angled approach that")
        print("  accumulates the required ground distance along Y and then turns toward the face.")

    (OUT / "board_presentation.json").write_text(json.dumps({
        "can": {"diameter_m": CAN_D, "mass_kg": CAN_M, "strike_height_m": CAN_D / 2},
        "boards": rows,
        "reachable_face_on_from_flat_y_lane": [r["file"] for r in reach],
        "method": ("slab frame recovered from each OBJ's own face normals; a slab blocks travel "
                   "along its thickness axis, so the travel axis for a face strike is the axis its "
                   "thickness is most nearly parallel to; presented area is width x length"),
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {OUT / 'board_presentation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
