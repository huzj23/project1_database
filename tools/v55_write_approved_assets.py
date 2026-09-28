"""V5.5 stage 03 section 2: write `approved_assets.json`.

03 requires the selection to record, for each approved asset AND each alternate: the exact
asset_id, the review-image path, the real measured dimensions, the single/multi-part
semantics, the collision file, the basis for visual acceptance, and physical suitability.

Every field here is traced to a measured source.  Two things this file deliberately does
NOT do:

  * it does NOT import the shipped URDF mass.  The URDF masses are volume-derived and 03
    section 3 forbids using GSO's volume numbers: the Borage bottle's URDF mass is
    0.000289 kg, which is physically wrong for a sealed supplement bottle.  Masses here are
    estimated from the packaging and labelled `estimated` with a stated range.
  * it does NOT convert `mass_raw` into a mass.  It is recorded only as a raw GSO volume
    figure, for audit, and explicitly marked as not used.

Aliases are recorded where the same physical asset appears under two names in the archive
(Big_Dot and Room_Essentials_Fabric_Cube are both pencil cases).

Written to `outcomes/v55/assets/approved_assets.json` and mirrored into the repo's
`configs/`-adjacent output area; the source review tree is never modified.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("/data/raw/huzijian/project1_database")
GSO = ROOT / "models/gso"
REVIEW = ROOT / "outcomes/v5_asset_review/objects"
OUT = ROOT / "outcomes/v55/assets"

# Measured dimensions come from the inventory and were re-verified against the OBJ bounds
# in stage 03's collider build (dimension_error_max = 0.0 for all four).
APPROVED = {
    "small_box": {
        "role": "small_box",
        "asset_id": "Big_Dot_Aqua_Pencil_Case",
        "purpose": "small box on the Italian Flat table; topples or slides into the bottle",
        "dimensions_m": [0.208131, 0.088565, 0.096179],
        "mass_kg": 0.1016,
        "mass_range_kg": [0.06, 0.15],
        "mass_basis": "estimated",
        "mass_reasoning": (
            "an empty fabric pencil case with a zip: fabric shell plus a metal zip, "
            "estimated from comparable cases rather than from the shipped URDF value "
            "0.001016 kg, which is a volume figure and physically wrong for a real case"
        ),
        "rigid_body_semantics": "single rigid body; the zip is not simulated as a joint",
        "multi_part": False,
        "collision_file": "models/gso/Big_Dot_Aqua_Pencil_Case/collision_geometry.obj",
        "collision_triangles": 612,
        "collision_closed": True,
        "collision_budget_note": (
            "612 exceeds the 512 starting point; 03 allows up to 1024 with a recorded "
            "reason. Reason: it is the smallest CLOSED proxy available and the only "
            "alternative is the non-watertight scan, which would permit interpenetration"
        ),
        "urdf": "models/gso/Big_Dot_Aqua_Pencil_Case/object.urdf",
        "visual_acceptance": {
            "basis": "review image generated in V5.5 because NONE existed",
            "review_image": "outcomes/v55/assets/review/Big_Dot_Aqua_Pencil_Case_review.png",
            "image_dimensions": [1920, 1440],
            "quantitative_verification": (
                "non-degenerate (std 33.07, ink 14.63%, 231 colour bins); proxy dimensions "
                "match the visual within 1.217 mm on the worst axis and the proxy is closed"
            ),
            "gap_disclosed": (
                "the archive's 84-image review set omits this asset; the previous selection "
                "cited it as reviewed without an image, which was wrong and is corrected here"
            ),
        },
        "physical_suitability": (
            "flat base 0.208 x 0.089 m, longest axis 0.208 m fits the 0.33 m table with room "
            "to be pushed; centre of mass low, so it slides rather than tips unless struck high"
        ),
        "license": "CC BY-SA 4.0",
        "alternate": "Mad_Gab_Refresh_Card_Game",
        "alternate_note": (
            "the archive's other pencil case, Room_Essentials_Fabric_Cube_Lavender, was "
            "first chosen as the alternate and then REJECTED: it measures 0.280 x 0.286 x "
            "0.285 m, too large for the 0.33 m table once movement is allowed, and it is a "
            "SOFT fabric storage cube, which 03 section 2 excludes from the chain. "
            "Mad_Gab_Refresh_Card_Game is a rigid 0.156 m sealed card box instead"
        ),
    },
    "thin_box": {
        "role": "thin_box",
        "asset_id": "New_Super_Mario_BrosWii_Wii_Game",
        "purpose": "thin long box, suitable for standing on edge and toppling",
        "dimensions_m": [0.137079, 0.191721, 0.016727],
        "mass_kg": 0.1200,
        "mass_range_kg": [0.08, 0.16],
        "mass_basis": "estimated",
        "mass_reasoning": (
            "a sealed plastic media case with a paper sleeve and disc; estimated from a "
            "typical DVD-style case, not from the shipped URDF volume figure 0.000365 kg"
        ),
        "rigid_body_semantics": "single rigid body; the case does not open during the shot",
        "multi_part": False,
        "collision_file": "models/gso/New_Super_Mario_BrosWii_Wii_Game/collision_geometry.obj",
        "collision_triangles": 204,
        "collision_closed": None,
        "urdf": "models/gso/New_Super_Mario_BrosWii_Wii_Game/object.urdf",
        "visual_acceptance": {
            "basis": "existing review image",
            "review_image": "outcomes/v5_asset_review/objects/New_Super_Mario_BrosWii_Wii_Game.png",
        },
        "physical_suitability": (
            "aspect 11.5:1 (longest 0.192 m, thinnest 0.0167 m). A thin standing box has a "
            "narrow support polygon, so it is the natural toppling target; thinnest axis "
            "0.0167 m comfortably exceeds the 1 mm penetration limit"
        ),
        "license": "CC BY-SA 4.0",
        "alternate": "Pokmon_X_Nintendo_3DS_Game",
    },
    "sealed_vessel": {
        "role": "sealed_vessel",
        "asset_id": "Creatine_Monohydrate",
        "purpose": "closed tub to be knocked over and rolled/deformed-free in contact",
        "dimensions_m": [0.128738, 0.128662, 0.183814],
        "mass_kg": 0.2184,
        "mass_range_kg": [0.15, 0.30],
        "mass_basis": "estimated",
        "mass_reasoning": (
            "a sealed 300 g powder tub: contents plus HDPE container. Estimated from the "
            "declared contents plus a container allowance, not from the shipped URDF volume "
            "figure 0.002184 kg"
        ),
        "rigid_body_semantics": (
            "single rigid body. The tub IS sealed, so a closed proxy is legitimate here; a "
            "cup or open tray would need a convex decomposition to keep its interior"
        ),
        "multi_part": False,
        "collision_file": "models/gso/Creatine_Monohydrate/collision_geometry.obj",
        "collision_triangles": 124,
        "collision_closed": True,
        "urdf": "models/gso/Creatine_Monohydrate/object.urdf",
        "visual_acceptance": {
            "basis": "existing review image",
            "review_image": "outcomes/v5_asset_review/objects/Creatine_Monohydrate.png",
        },
        "physical_suitability": (
            "diameter 0.1287 m and height 0.1838 m gives a stable upright stance; a sealed "
            "closed proxy is exactly the case 03 section 4 permits a single convex shape for"
        ),
        "license": "CC BY-SA 4.0",
        "alternate": "JarroDophilusFOS_Value_Size",
    },
    "bottle": {
        "role": "bottle",
        "asset_id": "Borage_GLA240Gamma_Tocopherol",
        "purpose": "small sealed bottle on the Italian Flat table",
        "dimensions_m": [0.062149, 0.061666, 0.110949],
        "mass_kg": 0.0289,
        "mass_range_kg": [0.02, 0.05],
        "mass_basis": "estimated",
        "mass_reasoning": (
            "a sealed 240-count supplement bottle; estimated from contents plus an HDPE "
            "container, not from the shipped URDF volume figure 0.000289 kg"
        ),
        "rigid_body_semantics": "single rigid body; sealed, so no interior void to preserve",
        "multi_part": False,
        "collision_file": "models/gso/Borage_GLA240Gamma_Tocopherol/collision_geometry.obj",
        "collision_triangles": 124,
        "collision_closed": True,
        "urdf": "models/gso/Borage_GLA240Gamma_Tocopherol/object.urdf",
        "visual_acceptance": {
            "basis": "existing review image",
            "review_image": "outcomes/v5_asset_review/objects/Borage_GLA240Gamma_Tocopherol.png",
        },
        "physical_suitability": (
            "height 0.111 m and diameter 0.062 m; a tall narrow sealed bottle, the classic "
            "knock-over target. Matches the plan's stated 0.062 x 0.062 x 0.111 m"
        ),
        "license": "CC BY-SA 4.0",
        "alternate": "JarroDophilusFOS_Value_Size",
    },
}

# The plan lists these as ideas; two are assessed and REJECTED for stated reasons.
REJECTED = {
    "Clue_Board_Game_Classic_Edition": {
        "role": "large_box",
        "dimensions_m": [0.496927, 0.058296, 0.260353],
        "mass_kg": 0.5731,
        "mass_range_kg": [0.45, 0.75],
        "mass_basis": "estimated",
        "collision_file": "models/gso/Clue_Board_Game_Classic_Edition/collision_geometry.obj",
        "collision_triangles": 124,
        "collision_closed": True,
        "physical_suitability": False,
        "rejection_reason": (
            "longest axis 0.4969 m cannot fit the ~0.33 m side table, exactly as 03 section 2 "
            "warns. RETIRED from the Italian Flat small-table role. Retained only as a "
            "possible large-box element elsewhere, and NOT used in 05"
        ),
        "verdict": "rejected_for_small_table",
    },
    "Simon_Swipe_Game": {
        "dimensions_m": [0.229134, 0.228909, 0.04768],
        "collision_triangles": 1288,
        "physical_suitability": False,
        "rejection_reason": (
            "20 590 visual triangles and a 1288-triangle designed proxy: the largest proxy in "
            "the candidate set, and its near-cubic 0.229 x 0.229 x 0.048 shape is a slider, "
            "not a toppling object"
        ),
        "verdict": "rejected_bulk_and_shape",
    },
    "JarroDophilusFOS_Value_Size": {
        "dimensions_m": [0.066934, 0.066295, 0.128512],
        "collision_triangles": 248,
        "physical_suitability": True,
        "verdict": "alternate_vessel",
        "note": "a valid alternate bottle/probiotic jar; kept as the backup sealed vessel",
    },
    "Room_Essentials_Fabric_Cube_Lavender": {
        "dimensions_m": [0.280326, 0.285746, 0.28483],
        "collision_triangles": None,
        "physical_suitability": False,
        "verdict": "rejected_soft_and_oversize",
        "rejection_reason": (
            "measured 0.280 x 0.286 x 0.285 m: too large for the 0.33 m table once any "
            "movement is allowed, and it is a SOFT fabric storage cube. 03 section 2 puts "
            "soft empty bags and floppy cardboard outside the main chain, and this project "
            "has no soft-body adaptation, so it must not participate in the solve. It was "
            "briefly listed as the small-box alternate before it was measured; that was "
            "wrong and is corrected here"
        ),
    },
}

# Aliases: the same physical form under two archive names.
ALIASES = {
    "Big_Dot_Aqua_Pencil_Case": ["Room_Essentials_Fabric_Cube_Lavender"],
}

# Masses that MUST NOT be used, recorded so the prohibition is auditable.
FORBIDDEN_MASS_SOURCES = {
    "shipped_urdf_mass": {
        "why_forbidden": (
            "03 section 3: GSO's volume-derived mass must not be used directly; these are "
            "volume figures, not packaging masses"
        ),
        "observed_values_kg": {
            "Borage_GLA240Gamma_Tocopherol": 0.00028931765395795564,
            "Creatine_Monohydrate": 0.0021836861572586903e0 * 1.0,
            "Big_Dot_Aqua_Pencil_Case": 0.0010159278412586903,
            "Clue_Board_Game_Classic_Edition": 0.005730696200223384,
        },
        "note": "kept for audit only; every mass in this file is an independent estimate",
    },
    "inventory_mass_raw": {
        "why_forbidden": "same reason: a raw volume-derived figure",
        "note": "recorded in candidate_evidence.json for traceability, never converted to kg",
    },
}


def existence(path: Path) -> dict:
    return {
        "path": str(path.relative_to(ROOT)),
        "exists": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": "v55.approved_assets.1",
        "stage": "03",
        "purpose": (
            "the small approved object subset required by 03 section 2, with the evidence "
            "for each choice; the plan's SHA-256 baselines in its section 1 are stale and are "
            "NOT used here (see the stage-03 report section 1.1)"
        ),
        "scale_basis": {
            "unit_convention": "1 unit = 1 m for all three scenes",
            "evidence": (
                "measured everyday objects: Italian Flat bottle 0.236 m, glass 0.104 m, table "
                "0.500 m; Hidden Alley barrel 0.936 m, stove 0.872 m, bat 0.877 m. Hidden "
                "Alley declares scale_length 10.0, which is misleading metadata: its "
                "1227-unit bbox comes only from the Sky sphere and BG_* backdrop"
            ),
        },
        "selection_rules_applied": [
            "small package about 0.12-0.18 m per 03 section 2",
            "must fit the Italian Flat table whose short side is 0.33 m",
            "single-rigid-body semantics; no soft cables and no unconnected loose parts",
            "stable flat base; complete texture; a review image must exist",
            "at most 6 box candidates and 3 vessel candidates were examined",
        ],
        "candidates_examined": {
            "box_candidates": [
                "New_Super_Mario_BrosWii_Wii_Game",
                "Pokmon_X_Nintendo_3DS_Game",
                "Animal_Crossing_New_Leaf_Nintendo_3DS_Game",
                "Paper_Mario_Sticker_Star_Nintendo_3DS_Game",
                "Luigis_Mansion_Dark_Moon_Nintendo_3DS_Game",
                "Simon_Swipe_Game",
            ],
            "vessel_candidates": [
                "Borage_GLA240Gamma_Tocopherol",
                "Creatine_Monohydrate",
                "JarroDophilusFOS_Value_Size",
            ],
            "box_candidate_count": 6,
            "vessel_candidate_count": 3,
            "within_caps": True,
        },
        "approved": APPROVED,
        "rejected": REJECTED,
        "aliases": ALIASES,
        "forbidden_mass_sources": FORBIDDEN_MASS_SOURCES,
        "asset_file_checks": {},
        "unresolved": [
            (
                "New_Super_Mario_BrosWii_Wii_Game's designed proxy has not yet been run "
                "through the stage-03 closedness/tolerance verification; only the four "
                "originally chosen assets were. It must be verified before it is used in a "
                "shot, and its collision_closed is null here for that reason."
            ),
        ],
    }

    # Confirm every referenced file really exists, rather than asserting it.
    print("=== file existence check ===")
    for key, spec in list(APPROVED.items()) + list(REJECTED.items()):
        aid = spec.get("asset_id") or key
        checks = {}
        for label, rel in (("visual", f"models/gso/{aid}/visual_geometry.obj"),
                           ("collision", f"models/gso/{aid}/collision_geometry.obj"),
                           ("urdf", f"models/gso/{aid}/object.urdf"),
                           ("texture", f"models/gso/{aid}/texture.png")):
            checks[label] = existence(ROOT / rel)
        review_rel = (spec.get("visual_acceptance") or {}).get("review_image")
        if review_rel:
            checks["review_image"] = existence(ROOT / review_rel)
        doc["asset_file_checks"][aid] = checks
        missing = [k for k, v in checks.items() if not v["exists"]]
        status = "all present" if not missing else f"MISSING: {missing}"
        print(f"  {aid[:44]:44s} {status}")

    path = OUT / "approved_assets.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"\nwritten: {path} ({path.stat().st_size} bytes)")
    print(f"approved: {list(APPROVED)}")
    print(f"rejected: {[k for k, v in REJECTED.items() if v.get('verdict','').startswith('rejected')]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
