#!/usr/bin/env bash
# ===========================================================================
# DECISIVE TEST: is the elephant's texture actually loaded, and by what mechanism?
#
# visual/model.obj says `mtllib visual_geometry.mtl` but the directory contains
# `model.mtl`, so the reference looks broken -- yet a built scene showed
# material_0 with TEX_IMAGE texture.png correctly wired.  All 6 GSO assets share this
# pattern, so if it is broken it is systemic; if it works, it is the established
# convention and must not be "fixed".
#
# Test by importing the OBJ the way the pipeline does, three ways:
#   as_is      : exactly as shipped
#   no_mtl     : model.mtl deleted      -> does the texture survive?
#   renamed    : model.mtl -> visual_geometry.mtl (the name the OBJ asks for)
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
E="$REPO/assets/objects/special_plush_elephant/visual"
T="$WS/tmp/objtest"; rm -rf "$T"; mkdir -p "$T"

echo "=== 0. render_import_kwargs recorded for the elephant ==="
"$PY" -c "
import yaml
m=yaml.safe_load(open('assets/objects/special_plush_elephant/asset.yaml'))
print('  visual =', m.get('visual'))
print('  visual_transform =', m.get('visual_transform'))
print('  render_import_kwargs =', m.get('render_import_kwargs'))
" 2>&1 | sed 's/^/  /'

echo
echo "=== 1. how does Kubric import a FileBasedObject OBJ? ==="
KB=$(find third_party/phyco-sim -path '*kubric*' -name '*.py' 2>/dev/null | xargs grep -ln 'class FileBasedObject' 2>/dev/null | head -1)
echo "  source: $KB"
[ -n "$KB" ] && grep -n 'obj\|mtl\|import_scene\|use_materials\|split' "$KB" | head -20 | sed 's/^/    /'

echo
echo "=== 2. Blender import test (same call the pipeline makes) ==="
cp -r "$E" "$T/as_is"
cp -r "$E" "$T/no_mtl";   rm -f "$T/no_mtl/model.mtl"
cp -r "$E" "$T/renamed";  mv "$T/renamed/model.mtl" "$T/renamed/visual_geometry.mtl"

cat > /tmp/objtest.py <<'PY'
import bpy, sys, os
d = sys.argv[sys.argv.index("--") + 1]
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.obj(filepath=os.path.join(d, "model.obj"), use_split_objects=False)
print(f"OT [{os.path.basename(d)}]")
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    print(f"OT   mesh={o.name} slots={len(o.data.materials)}")
    for m in o.data.materials:
        if m is None:
            print("OT     slot=None"); continue
        imgs = [n.image.name for n in m.node_tree.nodes
                if n.type == "TEX_IMAGE" and n.image] if m.use_nodes else []
        print(f"OT     material={m.name} use_nodes={m.use_nodes} images={imgs}")
PY

for case in as_is no_mtl renamed; do
  "$BLENDER" --background --factory-startup --python /tmp/objtest.py -- "$T/$case" 2>&1 \
    | grep -aE '^OT' | sed 's/^/  /'
done

echo
echo "=== 3. all 6 GSO assets: does visual/ contain the MTL the OBJ names? ==="
"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import glob, os, re
for obj in sorted(glob.glob("assets/objects/gso_*/visual/*.obj")) + \
           sorted(glob.glob("assets/objects/special_plush_elephant/visual/*.obj")):
    d = os.path.dirname(obj)
    m = re.search(r'^mtllib\s+(\S+)', open(obj, errors="ignore").read(3000), re.M)
    ref = m.group(1) if m else None
    print(f"  {os.path.basename(os.path.dirname(d)):44s} mtllib={ref!r} present={sorted(os.path.basename(p) for p in glob.glob(d+'/*.mtl'))}")
PY
