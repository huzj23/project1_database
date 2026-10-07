"""Check what the layout records, so the emitted gap numbers are labelled honestly.

The first version of `emit_deliverables.py` printed a "median gap" of 141.4 mm, which does not look like the 48.56 mm
face-to-face spacing this project has quoted for the trunk. The reason is that it measured CENTRE-TO-CENTRE distance
between consecutive domino centres, while the quoted spacing is the FACE-TO-FACE clearance. Both are legitimate but
they are different quantities, and publishing the centre-to-centre one under the bare label "median gap" would read as
a contradiction of the engineering reports. So this prints the layout's own fields and both distances, computed from
the recorded extents and yaws.
"""

import json
import math
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
LAYOUT = ROOT / "tmp/v64_node12/layout_v65_tailwest_candidate_b.json"

L = json.loads(LAYOUT.read_text())
print("layout top-level keys:", list(L.keys()))
print("n objects:", len(L["objects"]))
o0 = L["objects"][0]
print("\nfirst object keys:", list(o0.keys()))
print(json.dumps(o0, ensure_ascii=False, indent=1)[:1400])

order = [r["id"] for r in L["objects"]]
by = {r["id"]: r for r in L["objects"]}


def half_along(r, ux, uy):
    """Half-extent of this box measured along the unit direction (ux, uy), in its own yaw frame.

    `yaw` in this layout is stored in RADIANS, not degrees: F44 records 2.356194490192345, which is 3*pi/4 = 135 deg,
    matching the placement report's "(0.80, 12.50, 135 deg)". An earlier revision of this probe wrapped it in
    `math.radians()` -- converting radians as though they were degrees -- and produced negative face-to-face gaps for
    the tail. The value is used as-is.
    """
    he = [d / 2.0 for d in r["dims"]]
    yaw = r.get("yaw", 0.0)
    # the mesh's local x axis, rotated into world
    ax, ay = math.cos(yaw), math.sin(yaw)
    bx, by = -math.sin(yaw), math.cos(yaw)
    return abs(ax * ux + ay * uy) * he[0] + abs(bx * ux + by * uy) * he[1]


print(f"\n{'from':>5}{'to':>6}{'centre_mm':>12}{'face_to_face_mm':>18}")
cc, ff = [], []
for a, b in zip(order, order[1:]):
    pa, pb = by[a]["settled_position"], by[b]["settled_position"]
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    d = math.hypot(dx, dy)
    ux, uy = (dx / d, dy / d) if d else (1.0, 0.0)
    gap = d - half_along(by[a], ux, uy) - half_along(by[b], ux, uy)
    cc.append(d)
    ff.append(gap)
    if a in ("F44", "F45", "F46", "F47", "F01", "F02", "F03") or b in ("F48",):
        print(f"{a:>5}{b:>6}{1000 * d:>12.3f}{1000 * gap:>18.3f}")

ccs, ffs = sorted(cc), sorted(ff)
print(f"\ncentre-to-centre: median {1000 * ccs[len(ccs) // 2]:.3f} mm  range "
      f"{1000 * min(cc):.3f}..{1000 * max(cc):.3f}")
print(f"face-to-face:     median {1000 * ffs[len(ffs) // 2]:.3f} mm  range "
      f"{1000 * min(ff):.3f}..{1000 * max(ff):.3f}")

tail = [(a, b, d, g) for (a, b), d, g in zip(zip(order, order[1:]), cc, ff)
        if a in ("F43", "F44", "F45", "F46", "F47")]
print("\nV6.5 tail, both measures:")
for a, b, d, g in tail:
    print(f"  {a}->{b}: centre {1000 * d:8.3f} mm   face-to-face {1000 * g:8.3f} mm")
