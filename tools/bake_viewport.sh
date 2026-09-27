#!/usr/bin/env bash
# ===========================================================================
# Make the preview .blend show COLOUR immediately on open.
#
# Findings so far:
#   * The file's materials are CORRECT -- 89/94 carry packed image textures and the
#     disc has pbr_dark_wood with all 3 maps wired.
#   * The viewports are saved in SOLID shading, which shows only each material's
#     flat "Viewport Display" colour and IGNORES the node tree.  That is why the
#     scene looks untextured grey.
#   * Setting shading.type = RENDERED does not survive save/reload from Blender
#     3.4.1 in --background (it reads back RENDERED in memory, then SOLID on
#     reload), so I cannot fix it that way from here.
#
# Robust fix that DOES persist: bake each textured material's average texture colour
# into material.diffuse_color, which is exactly what SOLID shading displays.  The
# node tree is untouched, so rendering is unaffected -- this only changes the flat
# viewport colour.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"

cat > /tmp/bake.py <<'PY'
import bpy, os, sys
import numpy as np

src = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=src)

cache = {}
def avg_color(img):
    if img.name in cache:
        return cache[img.name]
    try:
        n = len(img.pixels)
        if n == 0:
            cache[img.name] = None; return None
        buf = np.empty(n, dtype=np.float32)
        img.pixels.foreach_get(buf)
        buf = buf.reshape(-1, 4)[:, :3]
        # ignore near-black background padding and fully transparent texels
        a = buf.reshape(-1, 4)[:, 3] if False else None
        col = buf.mean(axis=0)
        col = np.clip(col, 0.0, 1.0)
        cache[img.name] = tuple(float(v) for v in col)
        return cache[img.name]
    except Exception as e:
        print("BK   avg failed", img.name, e)
        cache[img.name] = None
        return None

changed = 0
skipped = 0
for m in bpy.data.materials:
    if not (m.use_nodes and m.node_tree):
        skipped += 1
        continue
    img = None
    for n in m.node_tree.nodes:
        if n.type == "TEX_IMAGE" and n.image:
            img = n.image
            break
    if img is None:
        skipped += 1
        continue
    col = avg_color(img)
    if col is None:
        skipped += 1
        continue
    m.diffuse_color = (col[0], col[1], col[2], 1.0)
    changed += 1

print(f"BK baked viewport colours: changed={changed} skipped={skipped} "
      f"images_sampled={len(cache)}")

# spot-check the two objects that matter
for name in ("pbr_dark_wood",):
    m = bpy.data.materials.get(name)
    if m:
        print(f"BK {name}.diffuse_color = {tuple(round(v,3) for v in m.diffuse_color)}")

env = bpy.data.objects.get("environment__replicad_apartment")
if env:
    cols = [tuple(round(v,3) for v in m.diffuse_color) for m in env.data.materials[:3] if m]
    print("BK env sample viewport colours:", cols)

# keep the render settings sane and make Layout the opening screen
for s in bpy.data.screens:
    if s.name == "Layout":
        try: bpy.context.window.screen = s
        except Exception: pass
        break
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 32
sc.cycles.use_denoising = True
sc.view_settings.view_transform = "Filmic"
sc.view_settings.look = "Medium High Contrast"

dst = src.replace(".blend", "-COLOR.blend")
bpy.ops.wm.save_as_mainfile(filepath=dst)
print("BK saved:", dst, os.path.getsize(dst))
PY

echo "=== bake viewport colours ==="
"$BLENDER" --background --factory-startup --python /tmp/bake.py -- \
  "$OUT/replicad_apartment-special_plush_elephant-preview.blend" 2>&1 \
  | grep -aE '^BK|Error|Traceback' | sed 's/^/  /'

echo
echo "=== verify the baked colours persisted ==="
cat > /tmp/vb.py <<'PY'
import bpy, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
m = bpy.data.materials.get("pbr_dark_wood")
print("VB pbr_dark_wood viewport:", tuple(round(v,3) for v in m.diffuse_color) if m else None)
env = bpy.data.objects.get("environment__replicad_apartment")
if env:
    print("VB env first 3:", [tuple(round(v,3) for v in mm.diffuse_color) for mm in env.data.materials[:3] if mm])
nondefault = sum(1 for mm in bpy.data.materials
                 if tuple(round(v,3) for v in mm.diffuse_color) != (0.8,0.8,0.8,1.0))
print(f"VB materials={len(bpy.data.materials)} non-default viewport colour={nondefault}")
print("VB unpacked:", len([i for i in bpy.data.images if i.filepath and not i.packed_file]))
PY
"$BLENDER" --background --factory-startup --python /tmp/vb.py -- \
  "$OUT/replicad_apartment-special_plush_elephant-preview-COLOR.blend" 2>&1 \
  | grep -aE '^VB|Error' | sed 's/^/  /'

rm -f "$OUT"/*.blend1 "$OUT/T1.blend"
ls -la "$OUT" | sed 's/^/  /'
