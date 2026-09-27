#!/usr/bin/env bash
# ===========================================================================
# Hypothesis D: Blender only restores a file's SCREENS (and therefore the saved
# viewport shading mode) when the "Load UI" preference is enabled.  In background
# mode --factory-startup, use_load_ui is likely False, so the reload I measured
# showed the factory SOLID layout and told me nothing about the file's contents.
#
# Test it directly: read use_load_ui, set it True, then open the file and read the
# shading back.  If the file really does carry RENDERED, the user (whose default is
# Load UI = on) will see colour on open.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
OUT="$WS/outcomes/_hf_preview"

cat > /tmp/ui.py <<'PY'
import bpy, sys
src = sys.argv[sys.argv.index("--") + 1]
fp = bpy.context.preferences.filepaths
print("UI use_load_ui BEFORE:", fp.use_load_ui)
fp.use_load_ui = True
print("UI use_load_ui SET   :", fp.use_load_ui)
bpy.ops.wm.open_mainfile(filepath=src)
d = {}
for s in bpy.data.screens:
    for a in s.areas:
        if a.type == "VIEW_3D":
            for sp in a.spaces:
                if sp.type == "VIEW_3D":
                    d[sp.shading.type] = d.get(sp.shading.type, 0) + 1
print("UI shading modes:", d)
print("UI screens:", [s.name for s in bpy.data.screens][:12])
PY

echo "=== read the file WITH use_load_ui forced True ==="
"$BLENDER" --background --factory-startup --python /tmp/ui.py -- "$OUT/T1.blend" 2>&1 \
  | grep -aE '^UI|Error' | sed 's/^/  /'

echo
echo "=== also check the ORIGINAL (unmodified) preview file ==="
"$BLENDER" --background --factory-startup --python /tmp/ui.py -- \
  "$OUT/replicad_apartment-special_plush_elephant-preview.blend" 2>&1 \
  | grep -aE '^UI|Error' | sed 's/^/  /'
