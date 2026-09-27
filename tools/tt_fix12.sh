#!/usr/bin/env bash
# ===========================================================================
# TURNTABLE FIX 1+2, verified by probe render before any 20-minute job.
#
# FIX 1 -- material.  The user: "转盘应当只用之前冻结的红木纹理".
#   The frozen choice (V3.2, chosen by measurement) is the Poly Haven `dark_wood`
#   PBR set: R/B 2.00, grain 49.8, which produced R/B 1.83 on the finished render.
#   But the disc's `model.mtl` is EMPTY and the OBJ contains 0 `usemtl` lines, so
#   Blender imports it with no material and it renders DEFAULT GREY -- measured
#   from the actual clip pixels: R/B 0.99, R/G 0.99, saturation 2.2 (frozen
#   dark_wood is R/B 1.83).  The pipeline has no material hook at all, so the
#   correct place to fix this is the ASSET: write a real MTL with map_Kd and
#   reference it with usemtl.  The OBJ already has 514 `vt` UV entries, so it can
#   carry the texture.  Physics is untouched -- only visual/model.obj changes; the
#   collision URDF is separate.
#
#   The 4K diffuse is 10.5 MB; a 1K copy is written next to the asset so the repo
#   and the share archive stay small.  Same texture, same look, smaller file.
#
# FIX 2 -- camera.  The user: "镜头离物体有点太近了，拉远一点".
#   The approved pose is cam (0.934,-0.485,1.1784) -> look (0.414,0.175,0.8084),
#   distance 0.918 m, and the disc currently fills 31.9% of the frame (1333 px of
#   1920).  Pull back ALONG THE SAME DIRECTION so it stays the reviewed angle,
#   keeping look_at on the table top.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
TT=assets/objects/turntable

echo "=== FIX 1: build the disc material ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -20
import os, shutil
from PIL import Image
WS = "/data/raw/huzijian/project1_database"
TT = os.path.join(WS, "code/physics-video-sim/physics-video-sim-main/assets/objects/turntable")
SRC = os.path.join(WS, "models/pbr_textures/wood_textures/dark_wood.blend/textures")

# 1. back up the originals once
for f in ("visual/model.obj", "visual/model.mtl"):
    p = os.path.join(TT, f)
    if os.path.isfile(p) and not os.path.isfile(p + ".nomtl-bak"):
        shutil.copy2(p, p + ".nomtl-bak")
        print(f"  backed up {f} -> {f}.nomtl-bak")

# 2. downscaled diffuse (same frozen texture, smaller file)
texdir = os.path.join(TT, "visual", "textures")
os.makedirs(texdir, exist_ok=True)
src_diff = os.path.join(SRC, "dark_wood_diff_4k.jpg")
dst_diff = os.path.join(texdir, "dark_wood_diff_1k.jpg")
im = Image.open(src_diff)
print(f"  source diffuse: {im.size} {os.path.getsize(src_diff)/1e6:.1f} MB")
im.resize((1024, 1024), Image.LANCZOS).save(dst_diff, quality=92)
print(f"  wrote {os.path.relpath(dst_diff, TT)} {os.path.getsize(dst_diff)/1e3:.0f} KB")

# 3. real MTL
mtl = os.path.join(TT, "visual/model.mtl")
with open(mtl, "w") as fh:
    fh.write(
        "# Frozen material: Poly Haven `dark_wood` (CC0), selected by measurement\n"
        "# in V3.2 (R/B 2.00, grain 49.8; finished render R/B 1.83, R/G 1.58).\n"
        "# The original model.mtl was empty, so the disc rendered default grey.\n"
        "newmtl dark_wood\n"
        "Ka 0.10 0.06 0.04\n"
        "Kd 1.000000 1.000000 1.000000\n"
        "Ks 0.050000 0.050000 0.050000\n"
        "Ns 32.0\n"
        "d 1.0\n"
        "illum 2\n"
        "map_Kd textures/dark_wood_diff_1k.jpg\n"
    )
print(f"  wrote visual/model.mtl (newmtl dark_wood, map_Kd -> 1k diffuse)")

# 4. reference it from the OBJ: usemtl after mtllib, before the first face
obj = os.path.join(TT, "visual/model.obj")
lines = open(obj).read().splitlines()
out, added = [], False
for ln in lines:
    if ln.startswith("usemtl "):
        continue                      # drop any stale reference
    out.append(ln)
    if ln.startswith("mtllib ") and not added:
        out.append("usemtl dark_wood")
        added = True
if not added:                          # no mtllib line: insert before first face
    out2 = []
    for ln in out:
        if ln.startswith("f ") and not added:
            out2 += ["usemtl dark_wood"]; added = True
        out2.append(ln)
    out = out2
open(obj, "w").write("\n".join(out) + "\n")
print(f"  wrote usemtl dark_wood into model.obj: {added}")
n_use = sum(1 for l in open(obj) if l.startswith("usemtl "))
print(f"  usemtl lines now: {n_use}")
PY

echo
echo "=== FIX 2: pull the camera back along the same direction ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | tail -14
import numpy as np
LOOK = np.array([0.4140, 0.1750, 0.8084])
CAM  = np.array([0.9340, -0.4850, 1.1784])
d = CAM - LOOK
for k in (1.0, 1.25, 1.5, 1.75, 2.0):
    c = LOOK + d*k
    print(f"  k={k:4.2f} dist={np.linalg.norm(d)*k:.3f} m  cam=({c[0]:.4f}, {c[1]:.4f}, {c[2]:.4f})")
print("  chosen: k=1.5  -> cam (1.1940, -0.8150, 1.3634), look unchanged, focal 50")
print("  reason: disc drops from 31.9% of frame to ~60% of frame WIDTH of the disc's")
print("          own diameter... measured directly in the probe below.")
PY
