#!/usr/bin/env bash
# ===========================================================================
# Make the preview .blend OPEN WITH COLOUR.
#
# Cause of the grey-on-open: the saved screens use
#     shading.type = SOLID, color_type = MATERIAL
# SOLID shading shows only each material's flat "Viewport Display" colour and
# ignores the node tree entirely, so the PBR wood texture and the elephant's
# texture.png never appear.  Rendered (or Material Preview) shading is required.
#
# Also set sensible render/viewport defaults so the file is pleasant to open, and
# verify every image is still packed.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"

cat > /tmp/colorize.py <<'PY'
import bpy, os, sys

blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=blend)

# --- 1. every 3D viewport -> RENDERED, so textures are visible on open -------
n_view = 0
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue
        for space in area.spaces:
            if space.type != "VIEW_3D":
                continue
            space.shading.type = "RENDERED"
            # keep the world/lighting from the scene rather than a studio HDRI
            space.shading.use_scene_world_render = True
            n_view += 1
print("CZ viewports set to RENDERED:", n_view)

# --- 2. make the Layout screen the active one so that is what opens ---------
for i, screen in enumerate(bpy.data.screens):
    if screen.name == "Layout":
        bpy.context.window.screen = screen
        break

# --- 3. sane render settings for interactive preview ------------------------
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
# 32 spp keeps the viewport responsive; the production stills used 24.
sc.cycles.samples = 32
sc.cycles.use_denoising = True
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.view_settings.view_transform = "Filmic"
sc.view_settings.look = "Medium High Contrast"
if sc.camera is None:
    cam = bpy.data.objects.get("camera__side_perpendicular")
    if cam:
        sc.camera = cam
print("CZ engine:", sc.render.engine, "spp:", sc.cycles.samples, "camera:", sc.camera.name if sc.camera else None)

# --- 4. confirm everything is still packed ---------------------------------
unpacked = [i.name for i in bpy.data.images if i.filepath and not i.packed_file]
print(f"CZ images={len(bpy.data.images)} unpacked={len(unpacked)}")
for n in unpacked[:5]:
    print("CZ   unpacked:", n)

# --- 5. save a colour-on-open copy -----------------------------------------
dst = blend.replace(".blend", "-COLOR.blend")
bpy.ops.wm.save_as_mainfile(filepath=dst)
print("CZ saved:", dst, os.path.getsize(dst))
PY

echo "=== build the colour-on-open copy ==="
"$BLENDER" --background --factory-startup --python /tmp/colorize.py -- \
  "$OUT/replicad_apartment-special_plush_elephant-preview.blend" 2>&1 \
  | grep -aE '^CZ|Error|Traceback' | sed 's/^/  /'

echo
echo "=== verify the new file re-opens in RENDERED shading ==="
cat > /tmp/verify_color.py <<'PY'
import bpy, sys
blend = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=blend)
modes = {}
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    modes[space.shading.type] = modes.get(space.shading.type, 0) + 1
print("VF shading modes:", modes)
print("VF active screen:", bpy.context.window.screen.name)
print("VF unpacked:", len([i for i in bpy.data.images if i.filepath and not i.packed_file]))
print("VF lights:", len([o for o in bpy.data.objects if o.type == "LIGHT"]))
print("VF world:", bpy.context.scene.world.name if bpy.context.scene.world else None)
PY
"$BLENDER" --background --factory-startup --python /tmp/verify_color.py -- \
  "$OUT/replicad_apartment-special_plush_elephant-preview-COLOR.blend" 2>&1 \
  | grep -aE '^VF|Error' | sed 's/^/  /'

rm -f "$OUT"/*.blend1
echo
echo "=== outputs ==="
ls -la "$OUT" | sed 's/^/  /'
