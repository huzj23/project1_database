#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Fetch Poly Haven (CC0) PBR textures and HDRIs into the workspace.
#
# Layout produced:
#   models/pbr_textures/<category>/<name>.blend/textures/<name>_{diff,nor_gl,rough,disp}_4k.*
#       ^ exactly the naming convention phyco-sim's texture loaders scan for
#   models/hdri_hdr/<name>_4k.hdr
#       ^ plain .hdr, loaded directly by phyco_backdrops (no tarball needed)
#
# Poly Haven is CC0: no attribution required, commercial use permitted.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

PY="$WS/tools/conda_env/bin/python"
TEXROOT="$WS/models/pbr_textures"
HDRROOT="$WS/models/hdri_hdr"
mkdir -p "$TEXROOT" "$HDRROOT"

# name|category
TEXTURES=(
  "concrete_floor_worn_001|concrete_textures"   # the colleague's exact choice
  "concrete_floor_02|concrete_textures"
  "concrete_floor_worn_05|concrete_textures"
  "painted_plaster_wall|ground_textures"
  "plaster_brick_02|brick_textures"
)
# name
HDRIS=(
  "studio_small_09"      # the colleague's scenario-06 choice
  "studio_small_03"
  "empty_warehouse_01"   # the colleague's scenario-01..05 choice
  "photo_studio_01"
  "brown_photostudio_02"
)

echo "=== Poly Haven fetch ==="
echo "textures -> $TEXROOT"
echo "hdris    -> $HDRROOT"

echo
echo "--- PBR textures (4K) ---"
"$PY" - "$TEXROOT" "${TEXTURES[@]}" <<'PY'
import json, os, sys, urllib.request
root, items = sys.argv[1], sys.argv[2:]
API = "https://api.polyhaven.com/files/{}"
def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=60))

# map our output suffix -> polyhaven map key
WANT = [("diff",   "Diffuse",      "jpg"),
        ("nor_gl", "nor_gl",       "exr"),
        ("rough",  "Rough",        "jpg"),
        ("disp",   "Displacement", "png")]

for item in items:
    name, cat = item.split("|")
    try:
        files = get(API.format(name))
    except Exception as e:
        print(f"  SKIP {name}: API error {type(e).__name__}")
        continue
    dest = os.path.join(root, cat, f"{name}.blend", "textures")
    os.makedirs(dest, exist_ok=True)
    got = 0
    for suffix, key, ext in WANT:
        node = files.get(key)
        if not node:
            print(f"    - {name}: no '{key}' map")
            continue
        res = node.get("4k") or {}
        entry = res.get(ext) or next(iter(res.values()), None)
        if not entry or "url" not in entry:
            print(f"    - {name}: no 4k {ext} for '{key}'")
            continue
        out = os.path.join(dest, f"{name}_{suffix}_4k.{ext}")
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            got += 1
            continue
        try:
            req = urllib.request.Request(entry["url"], headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=600) as r, open(out, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            got += 1
            print(f"    + {os.path.basename(out)}  {os.path.getsize(out)//1024} KB")
        except Exception as e:
            print(f"    ! {name}/{suffix}: {type(e).__name__}: {e}")
    print(f"  {name}: {got}/{len(WANT)} maps")
PY

echo
echo "--- HDRIs (4K) ---"
"$PY" - "$HDRROOT" "${HDRIS[@]}" <<'PY'
import json, os, sys, urllib.request
root, names = sys.argv[1], sys.argv[2:]
API = "https://api.polyhaven.com/files/{}"
for name in names:
    out = os.path.join(root, f"{name}_4k.hdr")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        print(f"  have {os.path.basename(out)}")
        continue
    try:
        req = urllib.request.Request(API.format(name), headers={"User-Agent": "Mozilla/5.0"})
        files = json.load(urllib.request.urlopen(req, timeout=60))
        entry = files["hdri"]["4k"]["hdr"]
        req = urllib.request.Request(entry["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=900) as r, open(out, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        print(f"  + {os.path.basename(out)}  {os.path.getsize(out)//1024//1024} MB")
    except Exception as e:
        print(f"  SKIP {name}: {type(e).__name__}: {e}")
PY

echo
echo "=== result ==="
find "$TEXROOT" -type f | head -30 | sed 's/^/  /'
echo "  texture files: $(find "$TEXROOT" -type f | wc -l)"
ls -la "$HDRROOT" | sed 's/^/  /'
du -sh "$TEXROOT" "$HDRROOT" 2>/dev/null | sed 's/^/  /'
