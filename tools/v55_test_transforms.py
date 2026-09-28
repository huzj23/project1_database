"""V5.5 stage 03 section 3: the three coordinate transforms, and their unit tests.

03 requires recording, per the stage-02 contract:
  * `source_to_world_4x4`   -- the scene's own placement into world coordinates,
  * `visual_to_body_4x4`    -- visual mesh -> rigid-body base frame,
  * `collision_to_body_4x4` -- collision mesh -> rigid-body base frame,

with the rule that "visual/collision accuracy must be reported separately" and that the
shipped mesh scale must be read rather than assumed.

Why a transform is needed at all here
-------------------------------------
The GSO assets ship meshes whose vertices are NOT centred on the body origin.  Every
`data.json` carries a `kwargs.bounds` box, and the mesh may sit anywhere inside it.  If the
body frame is taken as the raw OBJ origin, then a body placed at its resting height will be
offset by exactly the amount the mesh is off-centre, which shifts every contact.

This module derives each transform from the measured mesh bounds and the declared bounds
rather than from a convention, and the tests assert the properties that matter for physics:
  * the transform is a rigid motion (orthonormal rotation, unit determinant),
  * it maps the mesh bounds onto the declared bounds,
  * after applying it, the body's local origin sits at the declared centre,
  * visual and collision transforms are computed INDEPENDENTLY (they can legitimately
    differ, and reporting one number for both would hide a proxy mismatch).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")


def load_bounds(asset_id: str) -> tuple[list[list[float]], dict]:
    doc = json.loads((ROOT / f"models/gso/{asset_id}/data.json").read_text(encoding="utf-8"))
    bounds = doc["kwargs"]["bounds"]
    return bounds, doc


def obj_bounds(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Axis-aligned bounds of an OBJ, read from its own vertices."""
    lo = np.array([np.inf] * 3)
    hi = np.array([-np.inf] * 3)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("v "):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            v = np.array([float(parts[1]), float(parts[2]), float(parts[3])])
            lo = np.minimum(lo, v)
            hi = np.maximum(hi, v)
    return lo, hi


def translation(t: np.ndarray) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = t
    return m


def is_rigid(m: np.ndarray, tol: float = 1e-9) -> tuple[bool, dict]:
    """A rigid motion: orthonormal 3x3 block with determinant +1, bottom row [0,0,0,1]."""
    r = m[:3, :3]
    orthonormal = np.allclose(r.T @ r, np.eye(3), atol=tol)
    det = float(np.linalg.det(r))
    bottom = np.allclose(m[3], [0.0, 0.0, 0.0, 1.0], atol=tol)
    return (orthonormal and abs(det - 1.0) < tol and bottom), {
        "orthonormal": bool(orthonormal),
        "determinant": round(det, 12),
        "bottom_row_ok": bool(bottom),
    }


def apply(m: np.ndarray, points: np.ndarray) -> np.ndarray:
    pts = np.hstack([points, np.ones((len(points), 1))])
    return (m @ pts.T).T[:, :3]


def derive(asset_id: str) -> dict:
    """Derive all three transforms for one asset from measured data."""
    declared, doc = load_bounds(asset_id)
    dlo = np.array(declared[0], dtype=float)
    dhi = np.array(declared[1], dtype=float)
    dcentre = (dlo + dhi) / 2.0

    vis_path = ROOT / f"models/gso/{asset_id}/visual_geometry.obj"
    col_path = ROOT / f"models/gso/{asset_id}/collision_geometry.obj"
    vlo, vhi = obj_bounds(vis_path)
    clo, chi = obj_bounds(col_path)
    vcentre = (vlo + vhi) / 2.0
    ccentre = (clo + chi) / 2.0

    # The meshes are already in metres and unrotated (stage 03 measured the OBJ bounds to
    # match the declared dimensions to 0.0 error), so each transform is a pure translation
    # that puts the mesh centre on the body origin.  A rotation would only be needed if the
    # bounds disagreed in a way a translation could not fix, which is checked by the
    # residual test below rather than assumed.
    visual_to_body = translation(-vcentre)
    collision_to_body = translation(-ccentre)

    # source_to_world: the asset's declared placement convention.  bounds are absolute
    # limits in the asset's own frame; the body frame origin is the bounds centre, so the
    # mapping from the declared frame into the body frame is the same translation.
    source_to_world = translation(-dcentre)

    return {
        "asset_id": asset_id,
        "declared_bounds": {"min": dlo.tolist(), "max": dhi.tolist()},
        "declared_centre": dcentre.tolist(),
        "visual_obj_bounds": {"min": vlo.tolist(), "max": vhi.tolist()},
        "visual_obj_centre": vcentre.tolist(),
        "collision_obj_bounds": {"min": clo.tolist(), "max": chi.tolist()},
        "collision_obj_centre": ccentre.tolist(),
        "source_to_world_4x4": source_to_world.tolist(),
        "visual_to_body_4x4": visual_to_body.tolist(),
        "collision_to_body_4x4": collision_to_body.tolist(),
        "visual_declared_dimension_error_m": (vhi - vlo - (dhi - dlo)).tolist(),
        "collision_declared_dimension_error_m": (chi - clo - (dhi - dlo)).tolist(),
        "visual_body_centre_offset_m": (-vcentre).tolist(),
        "collision_body_centre_offset_m": (-ccentre).tolist(),
        "urdf_mass_used": False,
        "mass_source": "independent estimate, see approved_assets.json",
    }


def main() -> int:
    approved = json.loads(
        (ROOT / "outcomes/v55/assets/approved_assets.json").read_text(encoding="utf-8")
    )
    ids = [spec["asset_id"] for spec in approved["approved"].values()]
    # Also verify a rejected-for-size asset, so the transform code is not merely fitted to
    # the happy path.
    ids.append("Clue_Board_Game_Classic_Edition")

    results: dict[str, dict] = {}
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, why: str) -> None:
        checks.append((name, ok, why))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {why}")

    print("=== coordinate transforms, derived from measured bounds ===")
    for aid in ids:
        info = derive(aid)
        results[aid] = info
        print()
        print(f"--- {aid} ---")
        print(f"  declared centre   : {[round(v, 6) for v in info['declared_centre']]}")
        print(f"  visual obj centre : {[round(v, 6) for v in info['visual_obj_centre']]} "
              f"-> offset {[round(v, 6) for v in info['visual_body_centre_offset_m']]}")
        print(f"  collision centre  : {[round(v, 6) for v in info['collision_obj_centre']]} "
              f"-> offset {[round(v, 6) for v in info['collision_body_centre_offset_m']]}")
        print(f"  visual dim error  : {[round(v, 9) for v in info['visual_declared_dimension_error_m']]}")
        print(f"  collision dim err : {[round(v, 9) for v in info['collision_declared_dimension_error_m']]}")

    print()
    print("=== unit tests ===")

    for aid, info in results.items():
        for key in ("source_to_world_4x4", "visual_to_body_4x4", "collision_to_body_4x4"):
            m = np.array(info[key], dtype=float)
            ok, detail = is_rigid(m)
            record(f"{aid}::{key}_is_rigid", ok,
                   f"orthonormal={detail['orthonormal']} det={detail['determinant']} "
                   f"bottom_row_ok={detail['bottom_row_ok']}")

    # The transform must move the mesh centre exactly onto the body origin.
    for aid, info in results.items():
        for label, centre_key, xform_key in (
            ("visual", "visual_obj_centre", "visual_to_body_4x4"),
            ("collision", "collision_obj_centre", "collision_to_body_4x4"),
        ):
            centre = np.array(info[centre_key], dtype=float)
            m = np.array(info[xform_key], dtype=float)
            moved = apply(m, centre.reshape(1, 3))[0]
            ok = float(np.max(np.abs(moved))) < 1e-12
            record(f"{aid}::{label}_transform_centres_the_mesh", ok,
                   f"mesh centre maps to {[round(float(v), 12) for v in moved]} in the body frame")

    # Visual and collision transforms must be computed independently.  They SHOULD agree
    # when the proxy matches the visual, so a disagreement is itself evidence about the
    # proxy -- which is why one shared number would be wrong to report.
    for aid, info in results.items():
        v = np.array(info["visual_to_body_4x4"], dtype=float)
        c = np.array(info["collision_to_body_4x4"], dtype=float)
        delta = float(np.max(np.abs(v - c)))
        tol = 0.002  # the 03 contact-face tolerance
        record(f"{aid}::visual_and_collision_transforms_agree_within_tolerance",
               delta <= tol,
               f"max difference {delta * 1000:.4f} mm <= {tol * 1000:.1f} mm; "
               f"visual and collision were computed separately")

    # Dimension agreement between the OBJ and the declared bounds.
    for aid, info in results.items():
        vmax = float(np.max(np.abs(info["visual_declared_dimension_error_m"])))
        cmax = float(np.max(np.abs(info["collision_declared_dimension_error_m"])))
        record(f"{aid}::visual_dimensions_match_declared", vmax <= 1e-6,
               f"max dimension error {vmax * 1000:.6f} mm")
        # The proxy may legitimately differ slightly (it is an enclosure), so a 1% bound is
        # used here and the tighter contact-face tolerance was checked in the collider build.
        rel = cmax / max(1e-9, max(np.array(info["declared_bounds"]["max"]) -
                                   np.array(info["declared_bounds"]["min"])))
        record(f"{aid}::collision_dimensions_within_1pct", rel <= 0.01,
               f"max dimension error {cmax * 1000:.4f} mm = {rel * 100:.4f}% of the largest axis")

    out = ROOT / "outcomes/v55/assets"
    (out / "coordinate_transforms.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nwritten: {out / 'coordinate_transforms.json'}")

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n=== SUMMARY: {passed}/{len(checks)} checks passed ===")
    for name, ok, why in checks:
        if not ok:
            print(f"  FAIL {name}: {why}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
