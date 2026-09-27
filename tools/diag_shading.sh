#!/usr/bin/env bash
# ===========================================================================
# Why did setting shading.type = RENDERED not persist across save/reload?
#
# Hypothesis A: the modification never took in memory.
# Hypothesis B: it took, but save_as_mainfile in --background does not write the
#               window-manager/screen data.
# Hypothesis C: loading with --factory-startup discards the file's screens.
#
# Test each explicitly: set -> read back in-session -> save -> reload (WITHOUT
# --factory-startup) -> read again.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
OUT="$WS/outcomes/_hf_preview"
SRC="$OUT/replicad_apartment-special_plush_elephant-preview.blend"

cat > /tmp/t1.py <<'PY'
import bpy, sys
src = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=src)

def modes():
    d = {}
    for s in bpy.data.screens:
        for a in s.areas:
            if a.type == "VIEW_3D":
                for sp in a.spaces:
                    if sp.type == "VIEW_3D":
                        d[sp.shading.type] = d.get(sp.shading.type, 0) + 1
    return d

print("T1 before set :", modes())
n = 0
for s in bpy.data.screens:
    for a in s.areas:
        if a.type == "VIEW_3D":
            for sp in a.spaces:
                if sp.type == "VIEW_3D":
                    sp.shading.type = "RENDERED"
                    n += 1
print("T1 set count  :", n)
print("T1 after set  :", modes())          # hypothesis A
dst = "/data/raw/huzijian/project1_database/outcomes/_hf_preview/T1.blend"
bpy.ops.wm.save_as_mainfile(filepath=dst)
print("T1 after save :", modes())          # did save mutate anything?
print("T1 saved:", dst)
PY
echo "=== step 1: set + save ==="
"$BLENDER" --background --factory-startup --python /tmp/t1.py -- "$SRC" 2>&1 \
  | grep -aE '^T1|Error' | sed 's/^/  /'

cat > /tmp/t2.py <<'PY'
import bpy, sys
src = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=src)
d = {}
for s in bpy.data.screens:
    for a in s.areas:
        if a.type == "VIEW_3D":
            for sp in a.spaces:
                if sp.type == "VIEW_3D":
                    d[sp.shading.type] = d.get(sp.shading.type, 0) + 1
print("T2 modes:", d)
PY
echo
echo "=== step 2a: reload T1.blend WITHOUT --factory-startup ==="
"$BLENDER" --background --python /tmp/t2.py -- "$OUT/T1.blend" 2>&1 | grep -aE '^T2|Error' | sed 's/^/  /'
echo "=== step 2b: reload T1.blend WITH --factory-startup ==="
"$BLENDER" --background --factory-startup --python /tmp/t2.py -- "$OUT/T1.blend" 2>&1 | grep -aE '^T2|Error' | sed 's/^/  /'
