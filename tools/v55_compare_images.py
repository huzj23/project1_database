"""V5.5 stage 03 section 6: numeric comparison of the source/runtime alignment images.

Blender's bundled Python has no Pillow, so the image pair produced by
`tools/v55_source_runtime_compare.py` is compared here with the server's Pillow instead.

The framing is identical by construction (same camera, lens, resolution, seed and frame), so the
comparison is meaningful:

  * the frame BORDER is background that neither stage touches, so it must match tightly -- that
    is the alignment check, and it would fail for any camera, resolution or frame mismatch;
  * the remaining difference must be CONFINED to the interaction region, where the layer build
    moves the four props out of the archived source static instances, and must not be diffuse
    across the image, which would indicate that lighting or materials had changed.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes/v55/scenes/italian_flat/alignment"


def main() -> int:
    pa = OUT / "source_as_authored.png"
    pb = OUT / "runtime_initial_state.png"
    report: dict = {}
    print("=" * 76)
    for p in (pa, pb):
        print(f"  {p.name}: exists={p.is_file()} bytes={p.stat().st_size if p.is_file() else 0}")
    if not (pa.is_file() and pb.is_file()):
        raise SystemExit("FATAL: one or both alignment images are missing")

    ia = Image.open(pa).convert("RGB")
    ib = Image.open(pb).convert("RGB")
    report["source_size"] = list(ia.size)
    report["runtime_size"] = list(ib.size)
    print(f"  sizes: source {ia.size}, runtime {ib.size}")
    if ia.size != ib.size:
        report["aligned"] = False
        report["error"] = "the two images have different sizes, so framing differs"
    else:
        na = np.asarray(ia, dtype=np.float32)
        nb = np.asarray(ib, dtype=np.float32)
        diff = np.abs(na - nb).max(axis=2)
        report["mean_abs_diff_0_255"] = round(float(diff.mean()), 6)
        report["max_abs_diff_0_255"] = round(float(diff.max()), 6)
        report["pixels_over_8"] = int((diff > 8).sum())
        report["pixels_over_8_fraction"] = round(float((diff > 8).mean()), 9)
        report["pixels_over_32"] = int((diff > 32).sum())
        report["pixels_over_32_fraction"] = round(float((diff > 32).mean()), 9)

        h, w = diff.shape
        b = 8
        border = np.concatenate([diff[:b, :].ravel(), diff[-b:, :].ravel(),
                                 diff[:, :b].ravel(), diff[:, -b:].ravel()])
        report["border_mean_abs_diff"] = round(float(border.mean()), 6)
        report["border_max_abs_diff"] = round(float(border.max()), 6)
        report["framing_aligned"] = bool(border.mean() < 2.0)

        # Diffuse-change test: compare the mean difference of coarse tiles. A change confined to
        # the table region leaves most tiles near zero; a global lighting or material change does
        # not. Tiles are 8x8 over the frame.
        th, tw = h // 8, w // 8
        tiles = np.array([[float(diff[i * th:(i + 1) * th, j * tw:(j + 1) * tw].mean())
                           for j in range(8)] for i in range(8)])
        report["tile_means"] = [[round(v, 4) for v in row] for row in tiles]
        report["tiles_over_2_gray"] = int((tiles > 2.0).sum())
        report["tiles_total"] = 64
        report["localised_change"] = bool((tiles > 2.0).sum() <= 16)
        top = np.dstack(np.unravel_index(np.argsort(-tiles, axis=None)[:5], tiles.shape))[0]
        report["top_changed_tiles_row_col"] = [[int(r), int(c)] for r, c in top]

        # Lighting/materials preserved: the mean over the whole frame should stay small, since
        # only the props move.
        report["global_mean_abs_diff_0_255"] = round(float(diff.mean()), 6)
        report["lighting_material_stable"] = bool(float(diff.mean()) < 8.0)

        print(f"\n  mean |diff| {report['mean_abs_diff_0_255']:.4f}/255  "
              f"max {report['max_abs_diff_0_255']:.1f}")
        print(f"  pixels >8: {report['pixels_over_8']} "
              f"({report['pixels_over_8_fraction']*100:.4f}%), "
              f">32: {report['pixels_over_32']} "
              f"({report['pixels_over_32_fraction']*100:.4f}%)")
        print(f"  border mean |diff| {report['border_mean_abs_diff']:.4f} "
              f"(max {report['border_max_abs_diff']:.1f}) -> "
              f"framing aligned: {report['framing_aligned']}")
        print(f"  tiles over 2 gray: {report['tiles_over_2_gray']}/64 -> "
              f"change localised: {report['localised_change']}")
        print(f"  top changed tiles (row,col): {report['top_changed_tiles_row_col']}")
        print(f"  lighting/material stable: {report['lighting_material_stable']}")
        print("\n  tile mean |diff| grid (8x8 over the frame):")
        for row in tiles:
            print("   " + " ".join(f"{v:6.2f}" for v in row))

        # The three acceptance conditions, all required together:
        #   1. framing aligned -- the frame border is untouched background, so it must match;
        #   2. the change is LOCALISED -- only the table tiles where the props were re-layered
        #      may differ, because a diffuse change would mean lighting or materials moved;
        #   3. lighting/materials stable -- the whole-frame mean must stay small.
        report["acceptance"] = {
            "framing_aligned": bool(report["framing_aligned"]),
            "change_localised": bool(report["localised_change"]),
            "lighting_material_stable": bool(report["lighting_material_stable"]),
        }
        report["pass"] = bool(all(report["acceptance"].values()))
        print(f"\n  acceptance: {report['acceptance']}")
    report["aligned"] = bool(report.get("framing_aligned"))

    p = OUT / "image_comparison.json"
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")
    print(f"\nALIGNMENT IMAGES: {'PASS' if report.get('pass') else 'FAIL'}")
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
