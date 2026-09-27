"""Contact sheet for the "A" main track: one mid-clip frame per rendered job.

Rows = GSO actor, columns = motion variant, so the whole batch can be reviewed
at a glance.  ASCII labels only (cv2's Hershey fonts cannot draw CJK).

    blender.exe --background --factory-startup --python tools/compose_real_sheet.py
"""

from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "outcomes", "dataset_real")

ACTORS = [
    ("elephant", "plush elephant"),
    ("roomessentialsfabr", "fabric cube"),
    ("cardgame", "card game box"),
    ("gp16acoral", "plant pot coral"),
    ("lime", "orchid pot lime"),
    ("vanilla", "protein can"),
]
MOTIONS = [
    ("circular", "r075_p50", "circular r=0.75x"),
    ("circular", "r110_p35", "circular r=1.10x"),
    ("damped", "t25_k055", "damped t=2.5x"),
    ("damped", "t38_k085", "damped t=3.8x"),
    ("rotation", "az_p40", "spin Z 4.0s"),
    ("rotation", "ay_p30", "spin Y 3.0s"),
]

CELL_W, CELL_H = 320, 180
LABEL_H = 20
BAR_H = 30


def mid_frame(tag):
    d = os.path.join(ROOT, tag)
    if not os.path.isdir(d):
        return None, None
    frames = sorted(f for f in os.listdir(d)
                    if f.startswith("rgba_") and f.endswith(".png"))
    if not frames:
        return None, None
    img = cv2.imread(os.path.join(d, frames[len(frames) // 2]))
    meta = None
    mj = os.path.join(d, "sample.json")
    if os.path.isfile(mj):
        with open(mj, encoding="utf-8") as fh:
            meta = json.load(fh)
    if img is None:
        return None, meta
    return cv2.resize(img, (CELL_W, CELL_H), interpolation=cv2.INTER_AREA), meta


def main():
    cols, rows = len(MOTIONS), len(ACTORS)
    W = cols * CELL_W
    H = BAR_H + rows * (LABEL_H + CELL_H)
    sheet = np.full((H, W, 3), 24, np.uint8)

    cv2.putText(sheet,
                "PhyCo-Sim  track A  |  GSO scanned actors, HDRI warehouse backdrop, "
                "PBR ground  |  1280x720 / 24spp / 96 frames",
                (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (235, 235, 235), 1, cv2.LINE_AA)

    for c, (_m, _v, label) in enumerate(MOTIONS):
        cv2.putText(sheet, label, (c * CELL_W + 8, BAR_H + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (120, 220, 255), 1, cv2.LINE_AA)

    n_ok = 0
    pcts = []
    for r, (atag, alabel) in enumerate(ACTORS):
        y0 = BAR_H + r * (LABEL_H + CELL_H)
        for c, (motion, vtag, _l) in enumerate(MOTIONS):
            tag = f"{motion}_{atag}_{vtag}"
            cell, meta = mid_frame(tag)
            x, y = c * CELL_W, y0 + LABEL_H
            if cell is None:
                cv2.rectangle(sheet, (x + 1, y + 1), (x + CELL_W - 2, y + CELL_H - 2),
                              (55, 45, 75), -1)
                cv2.putText(sheet, "pending", (x + 120, y + CELL_H // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 220), 1, cv2.LINE_AA)
            else:
                sheet[y:y + CELL_H, x:x + CELL_W] = cell
                n_ok += 1
                if meta:
                    pcts.append(meta.get("actor_pct_of_frame_width", 0))
                    cv2.putText(sheet,
                                f"{meta.get('actor_pct_of_frame_width', 0):.0f}%",
                                (x + 8, y + CELL_H - 8), cv2.FONT_HERSHEY_SIMPLEX,
                                0.4, (120, 255, 120), 1, cv2.LINE_AA)
        cv2.putText(sheet, alabel, (8, y0 + LABEL_H + CELL_H - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 255, 180), 1, cv2.LINE_AA)

    out = os.path.join(ROOT, "OVERVIEW_track_A.png")
    cv2.imwrite(out, sheet)
    print(f"wrote {out}  ({sheet.shape[1]}x{sheet.shape[0]})  "
          f"{n_ok}/36 rendered", end="")
    if pcts:
        print(f"  actor%: min={min(pcts):.0f} median={np.median(pcts):.0f} max={max(pcts):.0f}")
    else:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
