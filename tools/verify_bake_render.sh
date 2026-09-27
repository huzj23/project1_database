#!/usr/bin/env bash
# ===========================================================================
# PROVE the viewport-colour bake did not affect RENDERING.
#
# I only set material.diffuse_color (the flat colour SOLID shading displays) and left
# every node tree untouched.  Cycles uses the node tree, so rendering should be
# identical -- but this project has a history of silent failures, so verify by
# rendering the COLOR file at low samples and measuring the disc.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"

cat > /tmp/rb.py <<'PY'
import bpy, sys, os
import numpy as np

blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=blend)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 8
sc.cycles.use_denoising = False
sc.render.resolution_x = 960
sc.render.resolution_y = 540
sc.render.filepath = "/data/raw/huzijian/project1_database/tmp/rb_out"
sc.render.image_settings.file_format = "PNG"
sc.render.use_compositing = False
sc.render.use_sequencer = False

# sanity: is the disc material's node tree still intact?
m = bpy.data.materials.get("pbr_dark_wood")
tex = [n.image.name for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
print("RB pbr_dark_wood viewport_color =", tuple(round(v,3) for v in m.diffuse_color))
print("RB pbr_dark_wood node textures  =", tex)
bc = [n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"][0].inputs["Base Color"]
print("RB base_color is_linked =", bc.is_linked)
print("RB unpacked images =", len([i for i in bpy.data.images if i.filepath and not i.packed_file]))

bpy.ops.render.render(write_still=True)
p = sc.render.filepath + ".png"
if not os.path.isfile(p):
    p = sc.render.filepath
img = bpy.data.images.load(p)
arr = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)[..., :3]
print("RB rendered:", p, arr.shape, "mean=", arr.mean().round(4))
# find the wood-coloured pixels (the disc) and the elephant texture
r, g, b = arr[...,0], arr[...,1], arr[...,2]
wood = (r > b*1.5) & (r > 0.02)
print(f"RB wood-ish pixels = {100*wood.mean():.2f}%  mean RGB = "
      f"{arr[wood].mean(axis=0).round(3) if wood.sum() else None}")
PY

for f in "replicad_apartment-special_plush_elephant-preview.blend" \
         "replicad_apartment-special_plush_elephant-preview-COLOR.blend"; do
  echo "=== $f ==="
  "$BLENDER" --background --factory-startup --python /tmp/rb.py -- "$OUT/$f" 2>&1 \
    | grep -aE '^RB|Error|Traceback' | sed 's/^/  /'
  echo
done
