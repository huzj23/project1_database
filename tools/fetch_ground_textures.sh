#!/usr/bin/env bash
# Download outdoor ground textures so each environment gets a matching floor:
#   street  -> asphalt
#   park    -> grass
#   sports  -> running track / rubberised
#
# A concrete floor under a park or a stadium was the biggest give-away that the
# backdrop was fake; the panorama has no ground of its own, so ours must match.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
ROOT="$WS/models/pbr_textures"
mkdir -p "$ROOT"

"$PY" - "$ROOT" <<'PY'
import json, os, sys, urllib.request

ROOT = sys.argv[1]
WANT = [
    ("asphalt_01",      "asphalt",  "street"),
    ("asphalt_floor",   "asphalt",  "street (alt)"),
    ("leafy_grass",     "grass",    "park"),
    ("grass_ground",    "grass",    "park (alt)"),
    ("running_track",   "sport",    "sports"),
    ("rubberized_track","sport",    "sports (alt)"),
]

def fetch(u, timeout=120):
    r = urllib.request.Request(u, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.read()

for slug, cat, label in WANT:
    outdir = os.path.join(ROOT, f"{cat}_textures", f"{slug}.blend", "textures")
    os.makedirs(outdir, exist_ok=True)
    have = [f for f in os.listdir(outdir)] if os.path.isdir(outdir) else []
    if len(have) >= 3:
        print(f"  {slug:<20} already present ({len(have)} maps)")
        continue
    try:
        info = json.loads(fetch(f"https://api.polyhaven.com/files/{slug}"))
    except Exception as e:
        print(f"  {slug:<20} API FAILED: {type(e).__name__}")
        continue

    got = []
    for key, suffix in (("Diffuse", "diff"), ("Rough", "rough"),
                        ("nor_gl", "nor_gl"), ("AO", "ao")):
        node = info.get(key)
        if not node:
            continue
        url = None
        for res in ("4k", "2k"):
            try:
                fmt = "jpg" if key in ("Diffuse", "Rough", "AO") else "jpg"
                if fmt in node.get(res, {}):
                    url = node[res][fmt]["url"]
                    break
                if "png" in node.get(res, {}):
                    url = node[res]["png"]["url"]
                    break
            except Exception:
                continue
        if not url:
            continue
        try:
            data = fetch(url)
            ext = os.path.splitext(url)[1]
            dest = os.path.join(outdir, f"{slug}_{suffix}_4k{ext}")
            open(dest, "wb").write(data)
            got.append(f"{suffix}{ext}")
        except Exception as e:
            print(f"    {slug} {key} download failed: {type(e).__name__}")

    size = sum(os.path.getsize(os.path.join(outdir, f)) for f in os.listdir(outdir))
    print(f"  {slug:<20} {len(got)} maps  {size/1048576:5.1f} MB   [{label}]")

print()
print("  === downloaded ground material sets ===")
for cat in sorted(os.listdir(ROOT)):
    d = os.path.join(ROOT, cat)
    if not os.path.isdir(d):
        continue
    for asset in sorted(os.listdir(d)):
        td = os.path.join(d, asset, "textures")
        if os.path.isdir(td):
            n = len(os.listdir(td))
            sz = sum(os.path.getsize(os.path.join(td, f)) for f in os.listdir(td))
            print(f"    {cat:<22} {asset:<26} {n} maps  {sz/1048576:6.1f} MB")
PY
