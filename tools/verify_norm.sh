#!/usr/bin/env bash
# ===========================================================================
# INDEPENDENT verification of the normalization.  Do not trust the summary --
# re-measure everything from the artifacts.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
E="assets/objects/special_plush_elephant"

echo "=== 1. elephant manifest ==="
cat "$E/asset.yaml" | sed 's/^/  /'

echo
echo "=== 2. collision mesh: tris, sha, frame agreement with the visual ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import hashlib, os
import numpy as np
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
E = f"{R}/assets/objects/special_plush_elephant"

def aabb_obj(p):
    pts = []
    for line in open(p, errors="ignore"):
        if line.startswith("v "):
            _, x, y, z = line.split()[:4]
            pts.append((float(x), float(y), float(z)))
    a = np.array(pts)
    return a.min(axis=0), a.max(axis=0), len(a)

def faces(p):
    return sum(1 for l in open(p, errors="ignore") if l.startswith("f "))

for tag, p in (("collision", f"{E}/collision/model.obj"), ("visual", f"{E}/visual/model.obj")):
    lo, hi, n = aabb_obj(p)
    print(f"  {tag:10s} verts={n:7d} faces={faces(p):7d}")
    print(f"             AABB min={np.round(lo,6).tolist()}")
    print(f"             AABB max={np.round(hi,6).tolist()}")
    print(f"             dims    ={np.round(hi-lo,6).tolist()}  max|v|={np.abs(np.array([lo,hi])).max():.6f}")

lo_c, hi_c, _ = aabb_obj(f"{E}/collision/model.obj")
lo_v, hi_v, _ = aabb_obj(f"{E}/visual/model.obj")
print(f"\n  FRAME CHECK (collision vs visual AABB delta):")
print(f"    min delta = {np.round(lo_c-lo_v, 6).tolist()}")
print(f"    max delta = {np.round(hi_c-hi_v, 6).tolist()}")
print(f"    => collision is in the SAME frame as visual: {bool(np.allclose(lo_c,lo_v,atol=0.01) and np.allclose(hi_c,hi_v,atol=0.01))}")
print(f"\n  mesh_sha256 = {hashlib.sha256(open(f'{E}/collision/model.obj','rb').read()).hexdigest()}")
print(f"  visual sha  = {hashlib.sha256(open(f'{E}/visual/model.obj','rb').read()).hexdigest()}")
PY

echo
echo "=== 3. manifest claims vs measured ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import sys, yaml, numpy as np
sys.path.insert(0, "src")
from physim.assets import AssetManager
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
m = yaml.safe_load(open(f"{R}/assets/objects/special_plush_elephant/asset.yaml"))
c = m["collision"]
print(f"  category      : {m['category']}   (must be 'special')")
print(f"  id            : {m['id']}   (must be 'special_plush_elephant')")
print(f"  license       : {m.get('license')}")
print(f"  source_sha256 : {str(m.get('source_sha256'))[:16]}...")
print(f"  collision.type: {c['type']}  tris={c.get('triangles')} verts={c.get('vertices')} max={c.get('max_triangles')}")
print(f"  mesh_sha256   : {str(c.get('mesh_sha256'))[:16]}...")
print(f"  bounding_radius={c.get('bounding_radius')}  footprint_radius={c.get('footprint_radius')}  support_height={c.get('support_height')}")
br, fr = c.get('bounding_radius'), c.get('footprint_radius')
print(f"  footprint<=bounding: {fr <= br}  ({fr} <= {br})")
print(f"  tris<=max: {c.get('triangles') <= c.get('max_triangles')}")
PY

echo
echo "=== 4. AssetManager loads the NEW id; OLD id is gone ==="
"$WS/tools/conda_env/bin/python" -u - <<'PY'
import sys
sys.path.insert(0, "src")
from physim.assets import AssetManager
am = AssetManager("configs/assets.yaml", "assets")
a = am.get("special_plush_elephant")
print(f"  new id OK: category={a.category} bounding_radius={a.collision.bounding_radius} support_height={a.support_height}")
try:
    am.get("gso_sootheze_cold_therapy_elephant"); print("  OLD ID STILL LOADS  <-- PROBLEM")
except Exception as e:
    print(f"  old id correctly gone: {type(e).__name__}")
print(f"  allowed_scenarios: {a.allowed_scenarios}")
PY

echo
echo "=== 5. live config references updated? (datasets/ must be untouched) ==="
grep -rn 'special_plush_elephant' configs/ 2>/dev/null | sed 's/^/  /'
echo "  --- any stale reference left in configs/? ---"
grep -rn 'gso_sootheze_cold_therapy_elephant' configs/ 2>/dev/null | sed 's/^/  /' || echo "  none (good)"

echo
echo "=== 6. apartment final state ==="
ls assets/environments/replicad_apartment/visual/ | sed 's/^/  visual: /'
ls assets/environments/replicad_apartment/source/ | sed 's/^/  source: /'
grep -nE 'sha256|source_page|source_sha256|cleanliness' assets/environments/replicad_apartment/asset.yaml configs/maps.yaml 2>/dev/null | head -12 | sed 's/^/  /'

echo
echo "=== 7. preflight ==="
bash "$WS/tools/preflight_full3.sh" 2>&1 | tail -3 | sed 's/^/  /'
