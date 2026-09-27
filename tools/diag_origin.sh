#!/usr/bin/env bash
# ===========================================================================
# ROOT CAUSE: the actor rests 7.1 cm HIGHER than position[2] + support_height.
#
# Rest z measured 0.15386, expected 0.08302, excess +0.07084 m.
#
# Hypothesis: the GSO URDF's origin is NOT at the geometry centre.  The asset
# manifest's support_height (0.08232) is half the bounding-box height, which is
# only the correct rest offset if the mesh origin sits at the box centre.  If the
# origin is elsewhere (e.g. at the base, or offset by the original scan frame),
# the body rests at a different height.
#
# Measure: the URDF's declared collision mesh, its actual vertex bounds, and the
# origin offset -- exactly the quantity `_compensate_urdf_origin_offset` in the
# vendored Kubric tries to handle.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
WS=/data/raw/huzijian/project1_database

echo "=== the GSO URDF ==="
cat "$WS/models/gso/Whey_Protein_Vanilla/object.urdf" | sed 's/^/  /'

echo
echo "=== collision mesh bounds (what the URDF points at) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import numpy as np, os, re
WS="/data/raw/huzijian/project1_database"
d=os.path.join(WS,"models/gso/Whey_Protein_Vanilla")
print("  files:", sorted(os.listdir(d)))
urdf=open(os.path.join(d,"object.urdf")).read()
m=re.search(r'filename="([^"]+)"', urdf)
print("  urdf mesh ref:", m.group(1) if m else None)
# also check the pipeline's own collision dir
pd=os.path.join(WS,"code/physics-video-sim/physics-video-sim-main/assets/objects/gso_whey_protein_vanilla")
print("  pipeline asset files:", sorted(os.listdir(pd)))
for sub in ("collision","visual"):
    p=os.path.join(pd,sub)
    if os.path.isdir(p):
        print(f"  {sub}/:", sorted(os.listdir(p)))
PY

echo
echo "=== compare support_height against real mesh bounds ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import numpy as np, os
WS="/data/raw/huzijian/project1_database"
pd=os.path.join(WS,"code/physics-video-sim/physics-video-sim-main/assets/objects/gso_whey_protein_vanilla")
for name in ("collision/model.obj","visual/model.obj"):
    p=os.path.join(pd,name)
    if not os.path.isfile(p):
        print(f"  {name}: MISSING"); continue
    V=[]
    for ln in open(p, errors="ignore"):
        if ln.startswith("v "):
            V.append([float(x) for x in ln.split()[1:4]])
    V=np.array(V)
    mn,mx=V.min(axis=0),V.max(axis=0)
    print(f"  {name}: verts={len(V)}")
    print(f"    bounds min={np.round(mn,5).tolist()}")
    print(f"    bounds max={np.round(mx,5).tolist()}")
    print(f"    extents  ={np.round(mx-mn,5).tolist()}")
    print(f"    half-height (z) = {(mx[2]-mn[2])/2:.5f}")
    print(f"    origin offset from box centre z = {(mn[2]+mx[2])/2:.5f}")
print()
print("  asset.yaml says support_height = 0.08232, bounding_radius = 0.120850")
PY
