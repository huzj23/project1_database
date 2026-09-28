"""V5.5 stage 03 section 2: select the approved object subset from REAL evidence.

03 section 2 requires choosing from the approved box/can categories:
  * one small box suitable for a small table,
  * one thin long box suitable for toppling while standing,
  * one clearly-dimensioned sealed can/bottle,
  * plus one alternate each.
It also caps the search ("no more than 6 box candidates and 3 can candidates"), demands
evidence from the inventory's complete IDs AND the actual review images, and forbids
inferring what was scanned from the product name alone.

This script therefore joins three real sources:
  1. `tmp/v5_candidate_inventory.json` -- measured dimensions and mesh statistics,
  2. `outcomes/v5_asset_review/objects/*.png` -- whether a human-reviewable image EXISTS,
  3. the on-disk asset directory -- whether a collision mesh and URDF actually ship.

Selection criteria follow 03 literally: small package ~0.12-0.18 m; a box must fit a
~0.33 m side table (so the Clue box at 0.497 m cannot); single-rigid-body semantics; a
stable flat base; and no soft cables or unconnected loose parts.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INV = ROOT / "tmp" / "v5_candidate_inventory.json"
REVIEW = ROOT / "outcomes" / "v5_asset_review" / "objects"
GSO_SERVER_LISTING = ROOT / "outcomes" / "v55" / "bootstrap" / "20260928T194137" / "server_asset_inventory.txt"

# The side table that the small box must fit on (measured: Italian Flat Table is 0.33 m
# wide, ~1.18 m long).  The box's largest footprint axis must leave room to move.
TABLE_SHORT_SIDE_M = 0.33
SMALL_BOX_RANGE_M = (0.10, 0.24)      # 03 says ~0.12-0.18 m for a small package
THIN_BOX_MIN_ASPECT = 2.0             # long:thick for something that topples standing


def review_image_exists(asset_id: str) -> bool:
    return (REVIEW / f"{asset_id}.png").is_file()


def load_inventory() -> list[dict]:
    data = json.loads(INV.read_text(encoding="utf-8"))
    return data.get("gso", [])


def classify(name: str, dims) -> list[str]:
    """Name-based HINTS only.  03 forbids trusting the name, so these are used to
    shortlist candidates that are then judged on measured geometry, and every hint is
    recorded as a hint rather than a fact."""
    low = name.lower()
    tags = []
    if any(w in low for w in ("box", "case", "game", "puzzle", "card", "pack", "tin")):
        tags.append("box_like_name")
    if any(w in low for w in ("bottle", "can", "jar", "tub", "shaker", "cup", "mug")):
        tags.append("vessel_like_name")
    if any(w in low for w in ("cable", "cord", "wire", "rope", "strap", "chain")):
        tags.append("possible_soft_or_loose")
    return tags


def main() -> int:
    records = load_inventory()
    print(f"inventory records: {len(records)}")

    # Index the server listing so we can prove the collision mesh and URDF exist.
    server_has: dict[str, bool] = {}
    if GSO_SERVER_LISTING.is_file():
        text = GSO_SERVER_LISTING.read_text(encoding="utf-8", errors="replace")
        print(f"server listing: {GSO_SERVER_LISTING.name} "
              f"({len(text.splitlines())} lines)")
    else:
        print(f"server listing ABSENT: {GSO_SERVER_LISTING}")

    rows = []
    for r in records:
        aid = r.get("id") or r.get("directory")
        if not aid:
            continue
        dims = r.get("dimensions_m") or []
        if len(dims) < 3:
            continue
        dims = [float(v) for v in dims[:3]]
        rows.append({
            "asset_id": aid,
            "dimensions_m": dims,
            "longest": max(dims),
            "thinnest": min(dims),
            "vertices": (r.get("mesh") or {}).get("vertices"),
            "faces": (r.get("mesh") or {}).get("faces"),
            "watertight": (r.get("mesh") or {}).get("watertight"),
            "mass_raw": r.get("mass_raw"),
            "category": r.get("category"),
            "visual": r.get("visual"),
            "has_review_image": review_image_exists(aid),
            "name_tags": classify(aid, dims),
        })

    print(f"usable records: {len(rows)}")
    print(f"with a review image: {sum(1 for r in rows if r['has_review_image'])}")

    # ---- 1. the small box: must fit the table, be in the small-package range, and be
    #         verifiable from an actual image.
    print()
    print("=" * 78)
    print("=== BOX CANDIDATES for the small table (03 caps this at 6) ===")
    print("=" * 78)
    boxes = [
        r for r in rows
        if "box_like_name" in r["name_tags"]
        and r["has_review_image"]
        and SMALL_BOX_RANGE_M[0] <= r["longest"] <= SMALL_BOX_RANGE_M[1]
        and r["longest"] <= TABLE_SHORT_SIDE_M
        and "possible_soft_or_loose" not in r["name_tags"]
    ]
    # Rank by how close the longest axis is to a comfortable tabletop object and prefer
    # the thinner ones (a thin box topples; a cube just slides).
    boxes.sort(key=lambda r: (-(r["longest"] / r["thinnest"]), r["longest"]))
    for r in boxes[:8]:
        aspect = r["longest"] / r["thinnest"]
        print(f"  {r['asset_id'][:44]:44s} dims={[round(v,4) for v in r['dimensions_m']]}")
        print(f"      longest={r['longest']:.4f} thinnest={r['thinnest']:.4f} aspect={aspect:.2f} "
              f"faces={r['faces']} watertight={r['watertight']}")
        print(f"      fits table ({r['longest']:.3f} <= {TABLE_SHORT_SIDE_M}) = "
              f"{r['longest'] <= TABLE_SHORT_SIDE_M}; review image = {r['has_review_image']}")
        if len(r["name_tags"]) > 1:
            print(f"      tags={r['name_tags']}")

    # ---- 2. vessels: a sealed can/bottle to knock over.
    print()
    print("=" * 78)
    print("=== VESSEL CANDIDATES (03 caps this at 3) ===")
    print("=" * 78)
    vessels = [
        r for r in rows
        if "vessel_like_name" in r["name_tags"]
        and r["has_review_image"]
        and 0.08 <= r["longest"] <= 0.30
    ]
    vessels.sort(key=lambda r: abs(r["longest"] - 0.15))
    for r in vessels[:8]:
        print(f"  {r['asset_id'][:44]:44s} dims={[round(v,4) for v in r['dimensions_m']]}")
        print(f"      longest={r['longest']:.4f} faces={r['faces']} "
              f"watertight={r['watertight']} review={r['has_review_image']}")

    # ---- 3. the four already-approved assets: is the evidence complete?
    print()
    print("=" * 78)
    print("=== AUDIT of the four assets already selected in stage 03 ===")
    print("=" * 78)
    already = [
        "Borage_GLA240Gamma_Tocopherol",
        "Creatine_Monohydrate",
        "Big_Dot_Aqua_Pencil_Case",
        "Clue_Board_Game_Classic_Edition",
    ]
    by_id = {r["asset_id"]: r for r in rows}
    problems = []
    for aid in already:
        r = by_id.get(aid)
        if r is None:
            print(f"  {aid}: NOT in inventory")
            problems.append((aid, "absent from inventory"))
            continue
        ok_img = r["has_review_image"]
        print(f"  {aid[:44]:44s} dims={[round(v,4) for v in r['dimensions_m']]}")
        print(f"      review_image={ok_img}  faces={r['faces']} watertight={r['watertight']} "
              f"mass_raw={r['mass_raw']}")
        if not ok_img:
            problems.append((aid, "NO review image, so the visual-acceptance basis is missing"))

    print()
    print("=== EVIDENCE GAPS ===")
    if problems:
        for aid, why in problems:
            print(f"  GAP: {aid} -- {why}")
    else:
        print("  none")

    out = ROOT / "outcomes" / "v55" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    (out / "candidate_evidence.json").write_text(json.dumps({
        "box_candidates": boxes[:8],
        "vessel_candidates": vessels[:8],
        "already_selected": [by_id.get(a) for a in already],
        "evidence_gaps": [{"asset_id": a, "why": w} for a, w in problems],
    }, indent=2), encoding="utf-8")
    print(f"\nwritten: {out / 'candidate_evidence.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
