#!/usr/bin/env bash
# Fetch dark hardwood veneers for the turntable disc (mahogany-like: reddish brown).
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
ROOT="$WS/models/pbr_textures"
mkdir -p "$ROOT"

"$PY" - "$ROOT" <<'PY'
import json, os, sys, urllib.request
ROOT = sys.argv[1]
WANT = [("cherry_veneer", "cherry / reddish hardwood"),
        ("american_walnut_veneer", "american walnut"),
        ("dark_wood", "dark wood")]

def fetch(u, t=180):
    r = urllib.request.Request(u, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(r, timeout=t) as f:
        return f.read()

for slug, label in WANT:
    outdir = os.path.join(ROOT, "wood_textures", f"{slug}.blend", "textures")
    os.makedirs(outdir, exist_ok=True)
    if len(os.listdir(outdir)) >= 3:
        print(f"  {slug:<24} already present ({len(os.listdir(outdir))} maps)")
        continue
    try:
        info = json.loads(fetch(f"https://api.polyhaven.com/files/{slug}"))
    except Exception as e:
        print(f"  {slug:<24} API FAILED: {type(e).__name__}")
        continue
    got = []
    for key, suffix in (("Diffuse", "diff"), ("Rough", "rough"), ("nor_gl", "nor_gl")):
        node = info.get(key)
        if not node:
            continue
        url = None
        for res in ("4k", "2k"):
            for fmt in ("jpg", "png"):
                try:
                    if fmt in node.get(res, {}):
                        url = node[res][fmt]["url"]; break
                except Exception:
                    continue
            if url:
                break
        if not url:
            continue
        try:
            data = fetch(url)
            ext = os.path.splitext(url)[1]
            open(os.path.join(outdir, f"{slug}_{suffix}_4k{ext}"), "wb").write(data)
            got.append(suffix)
        except Exception as e:
            print(f"    {slug} {key}: {type(e).__name__}")
    sz = sum(os.path.getsize(os.path.join(outdir, f)) for f in os.listdir(outdir))
    print(f"  {slug:<24} {len(got)} maps  {sz/1048576:5.1f} MB   [{label}]")

print()
for cat in ("wood_textures",):
    d = os.path.join(ROOT, cat)
    if os.path.isdir(d):
        for a in sorted(os.listdir(d)):
            td = os.path.join(d, a, "textures")
            if os.path.isdir(td):
                print(f"    {cat}/{a}: {len(os.listdir(td))} maps")
PY
