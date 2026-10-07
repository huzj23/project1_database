"""V6.5 -- emit the standalone deliverable files `layout.json` and `physics_config.json`.

The plan asks for the layout and the physics configuration as separate deliverables, not only inside the run manifest.
Both are copied from the artifacts that were ACTUALLY used -- the layout that was solved and rendered, and the same
physics manifest the solver loaded -- with their hashes, so a recipient can confirm the film was made from these
inputs and not from an edited copy.

The layout file also states the two things a reader would otherwise have to reconstruct: the tail's own spacing
(it is deliberately different from the trunk's) and which parts of the chain are boundary items with less margin.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes/v65/radio_scurve_domino/v65_20261007_final"

LAYOUT_SRC = ROOT / "tmp/v64_node12/layout_v65_tailwest_candidate_b.json"
MANIFEST_SRC = ROOT / "tmp/v64_node12/v64_physics_manifest_r2.json"
PLACEMENT = ROOT / "log/V6.5_placement_report_20261007.md"


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


layout = json.loads(LAYOUT_SRC.read_text())
man = json.loads(MANIFEST_SRC.read_text())

# the corridor spacing, computed from the layout rather than quoted from a report
import math
pts = {r["id"]: r["settled_position"] for r in layout["objects"]}
order = [r["id"] for r in layout["objects"]]
by = {r["id"]: r for r in layout["objects"]}


def half_along(r, ux, uy):
    """Half-extent along (ux, uy) in this box's own yaw frame.

    `yaw` is stored in RADIANS here (F44's 2.356194490192345 is 135 deg), so it must NOT be passed through
    `math.radians`. An earlier version did, and reported physically impossible negative clearances.
    """
    he = [d / 2.0 for d in r["dims"]]
    yaw = r.get("yaw", 0.0)
    ax, ay = math.cos(yaw), math.sin(yaw)
    bx, by_ = -math.sin(yaw), math.cos(yaw)
    return abs(ax * ux + ay * uy) * he[0] + abs(bx * ux + by_ * uy) * he[1]


gaps = []
for a, b in zip(order, order[1:]):
    pa, pb = pts[a], pts[b]
    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
    c2c = math.hypot(dx, dy)
    ux, uy = (dx / c2c, dy / c2c) if c2c else (1.0, 0.0)
    gaps.append({"from": a, "to": b,
                 "centre_to_centre_m": round(c2c, 6),
                 "face_to_face_m": round(c2c - half_along(by[a], ux, uy) - half_along(by[b], ux, uy), 6)})
tail_gaps = [g for g in gaps if g["from"] in ("F43", "F44", "F45", "F46", "F47")]
# sanity check against the value this project proved crossable, so the geometry here cannot silently drift from it
proven = 0.04856
f01f02 = next(g["face_to_face_m"] for g in gaps if g["from"] == "F01" and g["to"] == "F02")
if abs(f01f02 - proven) > 0.002:
    raise SystemExit(f"F01->F02 face-to-face is {f01f02:.6f} m but the proven trunk spacing is {proven}; "
                     f"the gap definition is wrong, refusing to publish it")
f2f = sorted(g["face_to_face_m"] for g in gaps)

out_layout = {
    "source": str(LAYOUT_SRC), "sha256": sha256(LAYOUT_SRC),
    "md5": hashlib.md5(LAYOUT_SRC.read_bytes()).hexdigest(),
    "placement_report": str(PLACEMENT), "placement_report_sha256": sha256(PLACEMENT),
    "frame": layout.get("frame") or layout.get("coordinate_system_statement"),
    "n_objects": len(layout["objects"]),
    "objects": layout["objects"],
    "spacing": {"face_to_face_median_m": f2f[len(f2f) // 2],
                "face_to_face_min_m": f2f[0], "face_to_face_max_m": f2f[-1],
                "measured_as": ("FACE-TO-FACE clearance between consecutive settled boxes, along the line joining "
                                "their centres, using each box's own dims and yaw; `centre_to_centre_m` is also "
                                "given because the two differ and the earlier bare 'median gap' figure of 141 mm was "
                                "the centre-to-centre measure"),
                "validation": {"F01_to_F02_face_to_face_m": f01f02,
                               "project_proven_trunk_spacing_m": proven,
                               "agree": bool(abs(f01f02 - proven) <= 0.002)},
                "gaps": gaps,
                "tail_gaps": tail_gaps,
                "note": ("the V6.5 tail was re-laid with its own spacing and mixes three different box sizes "
                         "(cranium, trivial, paper), so a single 'the tail spacing' figure is not well defined; the "
                         "per-pair values above are the delivered ones")},
    "boundary_items": [
        {"piece": "F22", "peak_tilt_deg": 97.25, "final_tilt_deg": 26.25,
         "note": "the repaired tape ring relays by rolling; its final tilt is low because it rolls, and it does "
                 "trigger F23"},
        {"piece": "F37", "peak_tilt_deg": 62.32, "final_tilt_deg": 59.75,
         "note": "settles 0.25 deg short of the older literal 60 deg line while still relaying"},
    ],
}
(OUT / "layout.json").write_text(json.dumps(out_layout, indent=2, ensure_ascii=False), encoding="utf-8")

out_phys = {
    "source": str(MANIFEST_SRC), "sha256": sha256(MANIFEST_SRC),
    "manifest_version": man.get("manifest_version"), "supersedes": man.get("supersedes"),
    "world": man.get("world"),
    "solver_settings_used": {"hz": 1920, "sim_s": 9.0, "mode": "upstream",
                             "layout_override": str(LAYOUT_SRC)},
    "divergence_resolution": man.get("divergence_resolution"),
    "n_objects": len(man.get("objects", {})),
    "objects": man.get("objects"),
    "forbidden_inputs": man.get("forbidden_inputs"),
    "open_issues": man.get("open_issues"),
}
(OUT / "physics_config.json").write_text(json.dumps(out_phys, indent=2, ensure_ascii=False), encoding="utf-8")

print(f"layout.json        ({len(out_layout['objects'])} objects, {len(gaps)} gaps)")
print(f"  face-to-face median {out_layout['spacing']['face_to_face_median_m'] * 1000:.3f} mm "
      f"(F01->F02 {f01f02 * 1000:.3f} mm vs proven {proven * 1000:.3f} mm)")
for g in tail_gaps:
    print(f"  tail {g['from']}->{g['to']}  centre {g['centre_to_centre_m'] * 1000:8.3f} mm  "
          f"face-to-face {g['face_to_face_m'] * 1000:8.3f} mm")
print(f"physics_config.json ({len(man.get('objects', {}))} objects)")
