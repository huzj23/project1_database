"""V5.5 stage 03: quantitative verification that the baseline renders are real images.

I cannot view images, so every visual claim must be numeric.  A render that is entirely
black, entirely uniform, or almost all one colour would indicate a lighting/compositor
failure rather than a successful reuse of the authored setup.  This measures:

  * mean / std / min / max luminance
  * the fraction of near-black and near-white pixels
  * a coarse 8x6 block-mean grid, so structure is visible without an image viewer
  * the distinct-colour count on a subsample

Run with the project python.  Accepts one or more PNG paths.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_png(path: Path):
    """Minimal PNG reader for the 16-bit RGB frames Blender writes.

    Uses zlib + the PNG filter algorithm directly so no third-party dependency (PIL,
    imageio) is required -- the project env may not have them and installing packages to
    inspect our own evidence would be the wrong dependency direction.
    """
    import struct
    import zlib

    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")

    pos = 8
    width = height = depth = colour = None
    idat = bytearray()
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos : pos + 4])
        ctype = raw[pos + 4 : pos + 8]
        data = raw[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break

    if depth != 16 or colour != 2:
        raise ValueError(f"expected 16-bit RGB, got depth={depth} colour={colour}")

    channels = 3
    bpp = 2 * channels
    stride = width * bpp
    decompressed = zlib.decompress(bytes(idat))

    prev = bytearray(stride)
    rows = []
    offset = 0
    for _ in range(height):
        ftype = decompressed[offset]
        offset += 1
        line = bytearray(decompressed[offset : offset + stride])
        offset += stride
        if ftype == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif ftype == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        rows.append(line)
        prev = line

    return width, height, rows


def analyse(path: Path) -> dict:
    width, height, rows = load_png(path)

    total = 0
    sum_l = 0.0
    sum_l2 = 0.0
    lo = 255.0
    hi = 0.0
    near_black = 0
    near_white = 0
    colours = set()

    # Coarse grid of block means for a text-visible shape summary.
    gx, gy = 8, 6
    blocks = [[0.0] * gx for _ in range(gy)]
    counts = [[0] * gx for _ in range(gy)]

    for y in range(height):
        line = rows[y]
        by = min(gy - 1, y * gy // height)
        for x in range(width):
            i = x * 6
            # 16-bit big-endian per channel; scale to 0..255.
            r = line[i] << 8 | line[i + 1]
            g = line[i + 2] << 8 | line[i + 3]
            b = line[i + 4] << 8 | line[i + 5]
            luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 257.0
            total += 1
            sum_l += luma
            sum_l2 += luma * luma
            lo = min(lo, luma)
            hi = max(hi, luma)
            if luma < 8.0:
                near_black += 1
            if luma > 247.0:
                near_white += 1
            bx = min(gx - 1, x * gx // width)
            blocks[by][bx] += luma
            counts[by][bx] += 1
            if (x % 37 == 0) and (y % 37 == 0):
                colours.add((r >> 4, g >> 4, b >> 4))

    mean = sum_l / total
    var = max(0.0, sum_l2 / total - mean * mean)

    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "mean_luma": round(mean, 3),
        "std_luma": round(var ** 0.5, 3),
        "min_luma": round(lo, 2),
        "max_luma": round(hi, 2),
        "near_black_fraction": round(near_black / total, 4),
        "near_white_fraction": round(near_white / total, 4),
        "sampled_distinct_colours": len(colours),
        "block_mean_grid": [
            [round(blocks[y][x] / max(1, counts[y][x]), 1) for x in range(gx)]
            for y in range(gy)
        ],
    }


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("usage: v55_check_render_quality.py <png> [<png> ...]")
        return 2

    results = []
    for path in paths:
        if not path.is_file():
            print(f"MISSING: {path}")
            continue
        try:
            info = analyse(path)
        except Exception as exc:
            print(f"FAILED {path.name}: {type(exc).__name__}: {exc}")
            continue
        results.append(info)
        print(f"=== {path.name} ===")
        for key in (
            "width", "height", "bytes", "mean_luma", "std_luma", "min_luma",
            "max_luma", "near_black_fraction", "near_white_fraction",
            "sampled_distinct_colours",
        ):
            print(f"  {key:26s}: {info[key]}")
        # A real interior render has structure: non-trivial std and not a flat field.
        verdict = (
            "PASS-looking"
            if info["std_luma"] > 5.0
            and info["near_black_fraction"] < 0.98
            and info["sampled_distinct_colours"] > 40
            else "SUSPECT (flat or black)"
        )
        print(f"  verdict                   : {verdict}")
        print("  block mean grid (8x6):")
        for row in info["block_mean_grid"]:
            print("    " + " ".join(f"{v:5.1f}" for v in row))
        print()

    out = Path(__file__).resolve().parent.parent / "outcomes/v55/bootstrap/20260928T194500/local_baseline/render_quality.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
