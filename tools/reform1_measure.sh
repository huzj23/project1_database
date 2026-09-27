#!/usr/bin/env bash
# ===========================================================================
# 改造 step 1: measure the scene's OWN floor, and learn how the pipeline consumes
# the environment collision block.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== how does the pipeline consume environment collision? ==="
grep -rn 'half_extents\|collision.*box\|surface_groups\|regions' \
    "$REPO/src/physim/maps/surface_sampler.py" 2>/dev/null | head -20 | sed 's/^/  /'
echo
echo "--- environment collision loading ---"
grep -rn 'collision' "$REPO/src/physim/physics/pybullet_backend.py" 2>/dev/null | head -20 | sed 's/^/  /'

echo
echo "=== measure the floor inside the BUILT scene.blend ==="
"$WS/tools/runtime/blender-3.4.1-linux-x64/blender" --background \
  "$REPO/assets/environments/replicad_apartment/visual/scene.blend" \
  --python-expr '
import bpy, numpy as np
objs = [o for o in bpy.data.objects if o.type == "MESH"]
print("  mesh objects:", [o.name for o in objs])
for o in objs:
    mw = np.array(o.matrix_world)
    n = len(o.data.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    o.data.vertices.foreach_get("co", co)
    co = co.reshape(n, 3)
    w = co @ mw[:3, :3].T + mw[:3, 3]
    print(f"  {o.name}: verts={n}")
    print(f"    world bounds min={np.round(w.min(axis=0),4).tolist()}")
    print(f"    world bounds max={np.round(w.max(axis=0),4).tolist()}")
    print(f"    extents={np.round(w.max(axis=0)-w.min(axis=0),4).tolist()}")
    zmin = w[:,2].min()
    # the floor = vertices within 5 cm of the lowest point
    slab = w[w[:,2] < zmin + 0.05]
    print(f"    lowest z={zmin:.5f}; verts within 5cm of it: {len(slab)}")
    if len(slab):
        print(f"    FLOOR footprint x=[{slab[:,0].min():.4f},{slab[:,0].max():.4f}]"
              f" y=[{slab[:,1].min():.4f},{slab[:,1].max():.4f}]")
        print(f"    FLOOR area = {(slab[:,0].max()-slab[:,0].min())*(slab[:,1].max()-slab[:,1].min()):.2f} m^2")
' 2>&1 | grep -E '^  ' | head -30
