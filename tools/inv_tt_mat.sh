#!/usr/bin/env bash
# ===========================================================================
# (a) render status for the unfinished motions
# (b) TURNTABLE MATERIAL: the user says the disc "应当只用之前冻结的红木纹理".
#     Find out what material the disc actually uses right now, and where the
#     frozen `dark_wood` texture lives, so the disc can be switched to it.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== render status ==="
echo "  --- camC (rolling, camera C) ---"
cat "$WS/tmp/camC_stdout.log" 2>/dev/null | tr -d '\r' | tail -8 | sed 's/^/    /'
echo "  --- t1c (damping) ---"
cat "$WS/tmp/t1c_stdout.log" 2>/dev/null | tr -d '\r' | tail -6 | sed 's/^/    /'
echo "  running: $(pgrep -af 'scripts/generate.py' | head -1)"
echo "  load: $(cut -d' ' -f1-3 /proc/loadavg)"

echo
echo "=== turntable asset.yaml (material?) ==="
cat assets/objects/turntable/asset.yaml 2>/dev/null | sed 's/^/  /'

echo
echo "=== turntable files ==="
find assets/objects/turntable -type f 2>/dev/null | sed 's/^/  /'

echo
echo "=== does the disc obj reference a material/texture? ==="
head -20 assets/objects/turntable/visual/model.obj 2>/dev/null | sed 's/^/  /'
echo "  --- mtl files ---"
ls -la assets/objects/turntable/visual/ 2>/dev/null | sed 's/^/  /'

echo
echo "=== where is the frozen dark_wood texture? ==="
grep -rn 'dark_wood' --include=*.yaml --include=*.json --include=*.py --include=*.md \
  configs/ src/ assets/ "$WS/log" "$WS/tools" 2>/dev/null | head -20 | sed 's/^/  /'

echo
echo "=== materials available in the environment blend (what we could reuse) ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY' 2>&1 | grep -vE 'gvfs|^Read blend' | tail -30
import bpy
p = "assets/environments/replicad_apartment/visual/scene.blend"
bpy.ops.wm.open_mainfile(filepath=p)
print(f"  materials in scene.blend: {len(bpy.data.materials)}")
for m in list(bpy.data.materials)[:25]:
    has_tex = any(n.type == 'TEX_IMAGE' for n in m.node_tree.nodes) if m.use_nodes else False
    print(f"    {m.name:40s} nodes={len(m.node_tree.nodes) if m.use_nodes else 0} tex={has_tex}")
print(f"  images: {[i.name for i in bpy.data.images][:15]}")
PY

echo
echo "=== how does the renderer assign the actor's material? ==="
grep -n 'material\|Material\|texture\|image' src/physim/render/blender_backend.py | head -25 | sed 's/^/  /'
