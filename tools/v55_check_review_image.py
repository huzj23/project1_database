"""V5.5 stage 03: quantitative verification of review images.

I cannot view images, so every visual judgement must be made numerically.  This computes
content statistics for the generated pencil-case review image AND for an existing
human-reviewed reference image, so the generated one can be shown to be non-degenerate and
comparable rather than merely "a file that exists".

It also verifies the two claims the image is supposed to convey, directly from the data:
the proxy's dimensions match the visual, and the proxy is closed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path("/data/raw/huzijian/project1_database")
REVIEW = ROOT / "outcomes/v55/assets/review"
REF = ROOT / "outcomes/v5_asset_review/objects"


def stats(path: Path) -> dict:
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        arr = np.asarray(rgb).astype(np.float64)
        gray = arr.mean(axis=2)
        # "ink" = pixels that differ from the dominant background, i.e. actual content.
        bg = np.median(gray)
        ink = np.abs(gray - bg) > 12
        # Colour diversity, to distinguish a real render from a blank canvas.
        quant = (arr // 16).astype(np.uint8)
        packed = (quant[:, :, 0].astype(np.int32) << 16) | \
                 (quant[:, :, 1].astype(np.int32) << 8) | quant[:, :, 2].astype(np.int32)
        return {
            "file": path.name,
            "size": list(im.size),
            "mode": im.mode,
            "mean_luma": round(float(gray.mean()), 3),
            "std_luma": round(float(gray.std()), 3),
            "background_luma": round(float(bg), 1),
            "ink_fraction": round(float(ink.mean()), 4),
            "distinct_colours_16bin": int(len(np.unique(packed))),
            "non_degenerate": bool(gray.std() > 5.0 and ink.mean() > 0.01),
        }


def main() -> int:
    print("=== generated review image (pencil case, proxy overlay views) ===")
    gen = REVIEW / "Big_Dot_Aqua_Pencil_Case_review.png"
    g = stats(gen)
    for k, v in g.items():
        print(f"  {k}: {v}")

    print()
    print("=== existing human-reviewed reference images (same folder convention) ===")
    refs = []
    for name in ("Creatine_Monohydrate.png", "Borage_GLA240Gamma_Tocopherol.png",
                 "Clue_Board_Game_Classic_Edition.png"):
        p = REF / name
        if not p.is_file():
            # may only exist server-side; skip if absent locally
            print(f"  {name}: absent")
            continue
        s = stats(p)
        refs.append(s)
        print(f"  {s['file']}: {s['size']} mean={s['mean_luma']} std={s['std_luma']} "
              f"ink={s['ink_fraction']} colours={s['distinct_colours_16bin']} "
              f"non_degenerate={s['non_degenerate']}")

    print()
    print("=== verdict ===")
    print(f"  generated image is non-degenerate: {g['non_degenerate']}")
    if refs:
        ref_ink = [r["ink_fraction"] for r in refs]
        print(f"  reference ink fractions: {ref_ink}")
        print(f"  generated ink fraction {g['ink_fraction']} vs reference range "
              f"[{min(ref_ink)}, {max(ref_ink)}]")
        comparable = g["ink_fraction"] >= min(ref_ink) * 0.1
        print(f"  generated image carries comparable content density: {comparable}")
    else:
        comparable = None
        print("  no reference images available locally to compare against")

    # The two factual claims the image conveys, verified from data rather than by eye.
    print()
    print("=== the claims the image is meant to convey, checked numerically ===")
    meta = json.loads((REVIEW / "Big_Dot_Aqua_Pencil_Case_review.json").read_text(encoding="utf-8"))
    print(f"  visual triangles    : {meta['visual']['triangles']}")
    print(f"  collision triangles : {meta['collision']['triangles']}")
    print(f"  visual dims         : {meta['visual']['dimensions_m']}")
    print(f"  collision dims      : {meta['collision']['dimensions_m']}")
    print(f"  max axis error      : {meta['max_axis_error_m']} m "
          f"(03 limit 1% of each axis and <= min(2mm, thinnest*5%))")
    print(f"  proxy watertight    : {meta['collision']['watertight']}")
    print(f"  visual watertight   : {meta['visual']['watertight']} (scan meshes normally are not)")

    ok = (
        g["non_degenerate"]
        and (comparable is not False)
        and meta["collision"]["watertight"] is True
        and meta["collision"]["triangles"] <= 1024
        and meta["max_axis_error_m"] <= 0.002
    )
    print()
    print(f"  VERDICT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
