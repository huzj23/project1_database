#!/usr/bin/env bash
# Precise audit: what pipeline files did I actually change, and what is their
# current state?  (The earlier `find -newermt` was useless because syncing reset
# every mtime.)
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

echo "=== vendor repo git status (my edits show up here) ==="
cd "$WS/code/vendor/phyco-sim" && git status --short 2>&1 | head -20 | sed 's/^/  /'

echo
echo "=== DIAG instrumentation still in blender_backend.py? ==="
grep -c 'DIAG' "$REPO/src/physim/render/blender_backend.py" 2>/dev/null | sed 's/^/  DIAG lines: /'
grep -c 'purge_stale_frames' "$REPO/src/physim/render/blender_backend.py" 2>/dev/null | sed 's/^/  purge_stale_frames refs: /'

echo
echo "=== probe settings that must be restored ==="
echo "  free_fall_gso.yaml resolution:"
grep -n 'resolution' "$REPO/configs/scenarios/free_fall_gso.yaml" | sed 's/^/    /'
echo "  server.yaml samples_per_pixel:"
grep -n 'samples_per_pixel' "$REPO/configs/server.yaml" | sed 's/^/    /'
echo "  server.yaml scenario_config:"
grep -n 'scenario_config' "$REPO/configs/server.yaml" | sed 's/^/    /'

echo
echo "=== indoor environment manifest (current) ==="
sed 's/^/  /' "$REPO/assets/environments/replicad_apartment/asset.yaml"

echo
echo "=== maps.yaml: the apartment support region ==="
grep -B2 -A6 'replicad_apartment' "$REPO/configs/maps.yaml" | sed 's/^/  /'

echo
echo "=== Q2: does the stage GLB carry its own floor? ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os, struct
WS = "/data/raw/huzijian/project1_database"
p = os.path.join(WS, "models/backgrounds/replicad/stages/frl_apartment_stage.glb")
print("  glb:", os.path.isfile(p), f"{os.path.getsize(p)/1048576:.1f} MB" if os.path.isfile(p) else "")
# read the glTF JSON chunk and list mesh names
with open(p, "rb") as f:
    magic, ver, length = struct.unpack("<III", f.read(12))
    clen, ctype = struct.unpack("<II", f.read(8))
    js = json.loads(f.read(clen).decode("utf-8", "ignore"))
names = [m.get("name", "?") for m in js.get("meshes", [])]
print(f"  meshes in stage glb: {len(names)}")
floors = [n for n in names if any(k in n.lower() for k in ("floor", "ground", "ceiling"))]
print(f"  floor/ground-named meshes: {floors if floors else '(none by name)'}")
print(f"  sample mesh names: {names[:10]}")
print(f"  nodes: {len(js.get('nodes', []))}, materials: {len(js.get('materials', []))}")
PY

echo
echo "=== Q2: what generates the indoor floor collision? ==="
ls -la "$REPO/scripts/generate_environment_surface_collision.py" 2>/dev/null | sed 's/^/  /'
head -30 "$REPO/scripts/generate_environment_surface_collision.py" 2>/dev/null | sed 's/^/  /'
