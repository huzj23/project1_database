"""Four-way backdrop comparison for the go/no-go decision.

Same GSO actor, same motion, same framing logic -- only the environment and the
indoor light balance change, so the decision rests on the backdrop alone.

Run through Blender's interpreter (it has the cv2 DLL paths):
    blender.exe --background --factory-startup --python tools/compose_backdrop_sheet.py
"""

from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "outcomes", "_背景对照")

PANELS = [
    ("elephant__wh", "A. HDRI warehouse  (ambient 0.05)",
     "panorama backdrop + PBR concrete; no parallax"),
    ("elephant__in_lo", "B. Interior  (sun 5, amb 0.05)",
     "real room; hard sun patch, deep shadow"),
    ("elephant__in_mid", "C. Interior  (sun 5, amb 0.25)",
     "real room; sun patch lifted a little"),
    ("elephant__in_soft", "D. Interior  (sun 2.2, amb 0.50)",
     "indoor-like: soft window light, natural bounce"),
]

CELL_W, CELL_H = 620, 349
LABEL_H = 46
BAR_H = 34


def mid_frame(tag):
    d = os.path.join(ROOT, tag)
    if not os.path.isdir(d):
        return None
    frames = sorted(f for f in os.listdir(d)
                    if f.startswith("rgba_") and f.endswith(".png"))
    if not frames:
        return None
    img = cv2.imread(os.path.join(d, frames[len(frames) // 2]))
    if img is None:
        return None
    return cv2.resize(img, (CELL_W, CELL_H), interpolation=cv2.INTER_AREA)


def main():
    notes = {}
    idx = os.path.join(ROOT, "samples_index.json")
    if os.path.isfile(idx):
        with open(idx, encoding="utf-8") as fh:
            for s in json.load(fh).get("samples", []):
                notes[s["tag"]] = s

    cols = len(PANELS)
    W = cols * CELL_W
    H = BAR_H + LABEL_H + CELL_H + 26
    sheet = np.full((H, W, 3), 26, np.uint8)

    cv2.putText(sheet,
                "Backdrop decision   |   same GSO actor + same framing   |   "
                "640x360 / 24spp / 32 frames",
                (12, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (240, 240, 240), 1, cv2.LINE_AA)

    for c, (tag, title, sub) in enumerate(PANELS):
        x = c * CELL_W
        cv2.putText(sheet, title, (x + 12, BAR_H + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 220, 255), 1, cv2.LINE_AA)
        cv2.putText(sheet, sub, (x + 12, BAR_H + 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (175, 175, 175), 1, cv2.LINE_AA)
        cell = mid_frame(tag)
        y = BAR_H + LABEL_H
        if cell is None:
            cv2.putText(sheet, "(missing)", (x + 220, y + CELL_H // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (90, 90, 220), 1, cv2.LINE_AA)
        else:
            sheet[y:y + CELL_H, x:x + CELL_W] = cell
        m = notes.get(tag)
        if m:
            cv2.putText(sheet,
                        "d={0:.2f}m   actor {1:.0f}% of frame width".format(
                            m["camera_distance_m"], m["actor_pct_of_frame_width"]),
                        (x + 12, y + CELL_H + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        (210, 255, 210), 1, cv2.LINE_AA)

    out = os.path.join(ROOT, "BACKDROP_compare.png")
    cv2.imwrite(out, sheet)
    print("wrote {0}  ({1}x{2})".format(out, sheet.shape[1], sheet.shape[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
