"""Verify rendered PNGs numerically, without an image viewer.

I cannot see images, so every visual claim in the stage-05 report has to come from measurement. This
script checks the things that actually matter for a delivery frame and that a file size alone cannot
establish:

  * the pixel dimensions are the ones the render mode claims (09 requires even dimensions and a
    specific 16:9 size, and a wrong size would silently invalidate the whole delivery)
  * the frame is not blank, single-colour, or fully transparent
  * two frames that should show different moments of the motion really do differ, and by how much
  * where the subject is: the bounding box of pixels that differ between the release frame and the
    strike frame, as a fraction of the frame, which is the quantitative stand-in for "is the action
    big enough on screen"

Standard library only: Blender's bundled Python has no PIL, and this runs in the system Python.
"""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path


def read_png(path: Path) -> dict:
    """Decode a PNG enough to read pixels."""
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{path.name} is not a PNG")
    pos = 8
    idat = bytearray()
    width = height = bitdepth = colortype = None
    while pos < len(raw):
        (length,) = struct.unpack(">I", raw[pos:pos + 4])
        ctype = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width, height, bitdepth, colortype = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat += data
        elif ctype == b"IEND":
            break
        pos += 12 + length
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[colortype]
    if bitdepth not in (8, 16):
        raise SystemExit(f"{path.name}: bit depth {bitdepth} not handled")
    # Blender writes 16-bit PNGs unless told otherwise, so 16-bit has to be handled rather than
    # rejected: the delivered frames were 16-bit and a checker that refused to read them would
    # report nothing about the actual output.
    bps = 2 if bitdepth == 16 else 1
    buf = zlib.decompress(bytes(idat))
    stride = width * channels * bps
    bpp = channels * bps
    rows, prev = [], bytearray(stride)
    p = 0
    for _ in range(height):
        f = buf[p]
        p += 1
        line = bytearray(buf[p:p + stride])
        p += stride
        for i in range(stride):          # undo the PNG filters, bytewise (valid for 8 and 16 bit)
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 0xFF
            elif f == 2:
                line[i] = (line[i] + b) & 0xFF
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif f == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        rows.append(bytes(line))
        prev = line
    return {"width": width, "height": height, "channels": channels, "bit_depth": bitdepth,
            "rows": rows}


def stats(path: Path) -> dict:
    img = read_png(path)
    w, h, ch, rows = img["width"], img["height"], img["channels"], img["rows"]
    bps = 2 if img["bit_depth"] == 16 else 1
    n = 0
    tot = 0
    mn, mx = 255, 0
    uniq = set()
    alpha_zero = 0
    for y in range(0, h, max(1, h // 200)):
        row = rows[y]
        for x in range(0, w, max(1, w // 200)):
            # Collapse 16-bit samples to 8-bit for comparison, so frames of either depth can be
            # measured and diffed against each other.
            px = [row[(x * ch + c) * bps] for c in range(ch)]
            lum = (px[0] * 299 + px[1] * 587 + px[2] * 114) // 1000
            tot += lum
            n += 1
            mn = min(mn, lum)
            mx = max(mx, lum)
            uniq.add(tuple(px[:3]))
            if ch == 4 and px[3] == 0:
                alpha_zero += 1
    return {"file": path.name, "width": w, "height": h, "channels": ch,
            "bit_depth": img["bit_depth"],
            "sampled": n, "mean_luma": tot / max(1, n), "min_luma": mn, "max_luma": mx,
            "distinct_colours_sampled": len(uniq),
            "transparent_fraction": alpha_zero / max(1, n)}


def diff(a: Path, b: Path) -> dict:
    ia = read_png(a)
    ib = read_png(b)
    wa, ha, ca, ra = ia["width"], ia["height"], ia["channels"], ia["rows"]
    wb, hb, cb, rb = ib["width"], ib["height"], ib["channels"], ib["rows"]
    if (wa, ha) != (wb, hb):
        return {"error": f"size mismatch {wa}x{ha} vs {wb}x{hb}"}
    bps_a = 2 if ia["bit_depth"] == 16 else 1
    bps_b = 2 if ib["bit_depth"] == 16 else 1
    changed = 0
    total = 0
    x0, y0, x1, y1 = wa, ha, -1, -1
    big = 0
    for y in range(ha):
        ra_ = ra[y]
        rb_ = rb[y]
        for x in range(wa):
            pa = [ra_[(x * ca + c) * bps_a] for c in range(3)]
            pb = [rb_[(x * cb + c) * bps_b] for c in range(3)]
            d = abs(pa[0] - pb[0]) + abs(pa[1] - pb[1]) + abs(pa[2] - pb[2])
            total += 1
            if d > 24:
                changed += 1
                if d > 90:
                    big += 1
                x0 = min(x0, x)
                x1 = max(x1, x)
                y0 = min(y0, y)
                y1 = max(y1, y)
    changed_frac = changed / max(1, total)
    out = {"a": a.name, "b": b.name, "pixels_compared": total,
           "changed_pixels_fraction": changed_frac,
           "strongly_changed_fraction": big / max(1, total)}
    if x1 >= 0:
        out["changed_bbox_px"] = [x0, y0, x1, y1]
        out["changed_bbox_fraction_of_frame"] = {
            "x0": x0 / wa, "x1": x1 / wa, "y0": y0 / ha, "y1": y1 / ha,
            "width": (x1 - x0 + 1) / wa, "height": (y1 - y0 + 1) / ha}
    return out


def main() -> int:
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "--diff":
        import json
        print(json.dumps(diff(Path(args[1]), Path(args[2])), indent=2))
        return 0
    for a in args:
        p = Path(a)
        if not p.is_file():
            print(f"MISSING {p}")
            continue
        s = stats(p)
        even = (s["width"] % 2 == 0 and s["height"] % 2 == 0)
        blank = (s["max_luma"] - s["min_luma"]) < 6
        print(f"{s['file']:16s} {s['width']}x{s['height']} ch{s['channels']} {s['bit_depth']}bit  "
              f"mean {s['mean_luma']:6.2f}  range {s['min_luma']:3d}-{s['max_luma']:3d}  "
              f"colours {s['distinct_colours_sampled']:5d}  "
              f"alpha0 {s['transparent_fraction']*100:5.1f}%  "
              f"even={'yes' if even else 'NO'}  blank={'YES' if blank else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
