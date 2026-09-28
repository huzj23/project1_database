#!/usr/bin/env bash
# V5.5 stage 03: Hidden Alley segfaults Blender 3.4.1 (rc=139).  09_assets says the
# validated render path for this scene is Blender 4.2.23, so test whether the project's
# own 4.2.23 build runs on this server at all, and whether it can open the scene.
#
# No system libraries are modified and nothing is installed system-wide.
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/v55_env.sh

B42="$WS/tools/runtime/blender-4.2.23-linux-x64/blender"
SCENE="$WS/models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"

echo "=== A. does the 4.2.23 binary exist? ==="
if [ -x "$B42" ]; then
  echo "  yes: $B42"
  ls -la "$WS/tools/runtime/blender-4.2.23-linux-x64/" | head -8 | sed 's/^/  /'
else
  echo "  NO -- 4.2.23 not extracted here"
  ls -la "$WS/tools/runtime/" | grep -i 4.2 | sed 's/^/  /'
fi

echo
echo "=== B. can 4.2.23 start (plain)? ==="
"$B42" --version 2>&1 | head -3 | sed 's/^/  /'
echo "  rc=$?"

echo
echo "=== C. can 4.2.23 start with the project runtime/lib? ==="
LD_LIBRARY_PATH="$WS/tools/runtime/lib:${LD_LIBRARY_PATH:-}" "$B42" --version 2>&1 | head -3 | sed 's/^/  /'

echo
echo "=== D. 3.4.1: how far does the Hidden Alley open get? (granular) ==="
# Open the file and stop immediately -- does the READ itself crash, or a later step?
LD_LIBRARY_PATH="$WS/tools/runtime/lib:${LD_LIBRARY_PATH:-}" \
"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background --factory-startup \
  --python-expr "
import bpy
print('STEP1 about to open', flush=True)
bpy.ops.wm.open_mainfile(filepath='${SCENE}')
print('STEP2 opened OK', flush=True)
print('STEP3 objects =', len(bpy.data.objects), flush=True)
print('STEP4 meshes  =', len(bpy.data.meshes), flush=True)
print('STEP5 materials=', len(bpy.data.materials), flush=True)
print('STEP6 images  =', len(bpy.data.images), flush=True)
" 2>&1 | grep -aE '^(STEP|Error|Traceback|Segmentation)' | sed 's/^/  /'
echo "  rc(3.4.1 open-only)=$?"

echo
echo "=== E. 4.2.23: open the same scene ==="
LD_LIBRARY_PATH="$WS/tools/runtime/lib:${LD_LIBRARY_PATH:-}" "$B42" --background --factory-startup \
  --python-expr "
import bpy
print('STEP1 about to open', flush=True)
bpy.ops.wm.open_mainfile(filepath='${SCENE}')
print('STEP2 opened OK', flush=True)
print('STEP3 objects =', len(bpy.data.objects), flush=True)
print('STEP4 meshes  =', len(bpy.data.meshes), flush=True)
print('STEP5 lights  =', len([o for o in bpy.data.objects if o.type=='LIGHT']), flush=True)
print('STEP6 cameras =', len([o for o in bpy.data.objects if o.type=='CAMERA']), flush=True)
print('STEP7 world   =', bpy.context.scene.world.name if bpy.context.scene.world else None, flush=True)
print('STEP8 tris    =', sum(len(o.data.loop_triangles) for o in bpy.data.objects if o.type=='MESH'), flush=True)
" 2>&1 | grep -aE '^(STEP|Error|Traceback|Segmentation)' | sed 's/^/  /'
echo "  rc(4.2.23 open-only)=$?"
