#!/usr/bin/env bash
# ===========================================================================
# Does the new disc material match the look the user previously APPROVED?
#
# My probe measures the disc at R/B 4.04-4.22, while V3.2 recorded R/B 1.83 for the
# approved render.  Those were taken with different render settings and over
# different regions, so the numbers are not comparable as-is.  Measure the APPROVED
# renders and the new probe with ONE identical method (central disc patch) to decide
# whether the material really matches, and whether the grain SCALE matches (the
# approved path applied uv_scale=1.6; mine uses the OBJ's native UVs).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
WS=/data/raw/huzijian/project1_database

"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -40
import os, glob
import numpy as np
from PIL import Image
import cv2
WS = "/data/raw/huzijian/project1_database"

CANDS = [
    ("approved _tt_final/mahogany_f00", f"{WS}/outcomes/_tt_final/mahogany_f00.png"),
    ("approved _tt_replay/replay_f00",  f"{WS}/outcomes/_tt_replay/replay_f00.png"),
    ("approved _tt_table/table_f00",    f"{WS}/outcomes/_tt_table/table_f00.png"),
    ("wood_variants/wood_dark",         f"{WS}/outcomes/_tt_wood_variants/wood_dark.png"),
    ("wood_variants/wood_mahogany",     f"{WS}/outcomes/_tt_wood_variants/wood_mahogany.png"),
    ("NEW probe k1.50",                 f"{WS}/outcomes/_tt_fix/TTFIX_k1.50.png"),
    ("NEW probe k1.00",                 f"{WS}/outcomes/_tt_fix/TTFIX_k1.00.png"),
]

def stats(img, cy, cx, half=60):
    p = img[cy-half:cy+half, cx-half:cx+half].astype(np.float32)
    r, g, b = p[...,0].mean(), p[...,1].mean(), p[...,2].mean()
    gray = cv2.cvtColor(p.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    grain = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    # dominant feature size via autocorrelation width (rough grain scale proxy)
    gg = gray.astype(np.float32) - gray.mean()
    if gg.std() > 1e-3:
        ac = np.fft.irfft2(np.abs(np.fft.rfft2(gg))**2)
        ac = ac / ac.flat[0]
        row = ac[0, :half]
        below = np.nonzero(row < 0.5)[0]
        scale = float(below[0]) if len(below) else float(half)
    else:
        scale = float('nan')
    return r, g, b, grain, scale

print(f"{'image':34s} {'size':>10s} {'R':>6s} {'G':>6s} {'B':>6s} {'R/B':>5s} "
      f"{'R/G':>5s} {'grain':>7s} {'featsz':>6s}")
for label, p in CANDS:
    if not os.path.isfile(p):
        print(f"{label:34s}  MISSING"); continue
    img = np.asarray(Image.open(p).convert("RGB"))
    h, w = img.shape[:2]
    # disc sits slightly below centre in these framings
    cy, cx = int(h*0.62), int(w*0.50)
    r, g, b, grain, scale = stats(img, cy, cx)
    print(f"{label:34s} {w}x{h:<6d} {r:6.1f} {g:6.1f} {b:6.1f} {r/max(b,1e-6):5.2f} "
          f"{r/max(g,1e-6):5.2f} {grain:7.1f} {scale:6.1f}")
print()
print("  V3.2 recorded for the approved render: R/B 1.83, R/G 1.58")
print("  grey disc (pre-fix, from the real clip): R/B 0.99, R/G 0.99, sat 2.2")
PY
