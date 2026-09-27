"""Compose the local A/B samples into one labelled comparison sheet.

Rows = actor/motion, columns = lighting variant, so the shadow difference is
readable at a glance.  Labels are ASCII on purpose: cv2.putText cannot render
CJK with the built-in Hershey fonts (they come out as '?').

Run through Blender's interpreter, which has the cv2 DLL paths configured:
    blender.exe --background --factory-startup --python tools/compose_compare_sheet.py
"""

from __future__ import annotations

import json
import os
import sys

import cv2
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "outcomes", "_本地样本")

ACTORS = [
    ("elephant", "GSO plush elephant  /  circular"),
    ("cube", "GSO fabric cube  /  damped"),
]
LIGHTS = [
    ("sun_amb_low", "sun key + ambient 0.05  (crisp shadow)"),
    ("sun_amb_mid", "sun key + ambient 0.15  (balanced)"),
    ("area_amb_low", "softbox key + ambient 0.05  (soft)"),
]

CELL_W, CELL_H = 480, 270
LABEL_H = 34
BAR_H = 30


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

    cols, rows = len(LIGHTS), len(ACTORS)
    W = cols * CELL_W
    H = BAR_H + rows * (LABEL_H + CELL_H)
    sheet = np.full((H, W, 3), 28, np.uint8)

    cv2.putText(sheet,
                "PhyCo-Sim local realism samples   |   GSO scanned object + PBR ground "
                "+ HDRI background   |   640x360 / 24spp / 32 frames",
                (10, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (235, 235, 235), 1, cv2.LINE_AA)

    for c, (_ltag, llabel) in enumerate(LIGHTS):
        cv2.putText(sheet, llabel, (c * CELL_W + 10, BAR_H + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (120, 220, 255), 1, cv2.LINE_AA)

    for r, (atag, alabel) in enumerate(ACTORS):
        y0 = BAR_H + r * (LABEL_H + CELL_H)
        cv2.putText(sheet, alabel, (10, y0 + LABEL_H + CELL_H - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (170, 255, 170), 1, cv2.LINE_AA)
        for c, (ltag, _ll) in enumerate(LIGHTS):
            tag = "{0}__{1}".format(atag, ltag)
            cell = mid_frame(tag)
            x, y = c * CELL_W, y0 + LABEL_H
            if cell is None:
                cv2.putText(sheet, "(missing)", (x + 150, y + CELL_H // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (90, 90, 220), 1, cv2.LINE_AA)
            else:
                sheet[y:y + CELL_H, x:x + CELL_W] = cell
            m = notes.get(tag)
            if m:
                cv2.putText(sheet,
                            "d={0:.2f}m  actor {1:.0f}% of width".format(
                                m["camera_distance_m"], m["actor_pct_of_frame_width"]),
                            (x + 10, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                            (255, 255, 255), 1, cv2.LINE_AA)

    out = os.path.join(ROOT, "COMPARE_sheet.png")
    cv2.imwrite(out, sheet)
    print("wrote {0}  ({1}x{2})".format(out, sheet.shape[1], sheet.shape[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
