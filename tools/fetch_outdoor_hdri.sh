#!/usr/bin/env bash
# Download outdoor HDRI candidates: street, nature, sports field.
#
# These are backdrop-only environments (a 4K equirectangular panorama plus a
# ground plane), so the question the review raises is exactly the right one:
# do they look as empty/flat as the bare interiors did, or do they carry enough
# structure to pass as a real place?
#
# Poly Haven's API is used to resolve asset -> file URLs, so no guessing.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
DEST="$WS/models/hdri_hdr"
mkdir -p "$DEST"

"$PY" - "$DEST" <<'PY'
import json, os, sys, urllib.request

DEST = sys.argv[1]
WANT = [
    ("kloppenheim_02",        "street (residential)"),
    ("german_town_street",    "street (town)"),
    ("autumn_park",           "nature (park)"),
    ("ballawley_park",        "nature (park)"),
    ("orlando_stadium",       "sports (stadium)"),
    ("soccerfield_02",        "sports (field)"),
]

def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

for slug, label in WANT:
    out = os.path.join(DEST, f"{slug}_4k.hdr")
    if os.path.isfile(out) and os.path.getsize(out) > 1_000_000:
        print(f"  {slug:<24} already present ({os.path.getsize(out)/1048576:.1f} MB)")
        continue
    try:
        info = json.loads(fetch(f"https://api.polyhaven.com/files/{slug}"))
    except Exception as e:
        print(f"  {slug:<24} API FAILED: {type(e).__name__}")
        continue
    # prefer 4k hdr
    url = None
    try:
        url = info["hdri"]["4k"]["hdr"]["url"]
    except Exception:
        for res in ("4k", "2k", "8k"):
            try:
                url = info["hdri"][res]["hdr"]["url"]
                break
            except Exception:
                continue
    if not url:
        print(f"  {slug:<24} no 4k hdr available")
        continue
    try:
        data = fetch(url, timeout=180)
        open(out, "wb").write(data)
        print(f"  {slug:<24} downloaded {len(data)/1048576:.1f} MB   [{label}]")
    except Exception as e:
        print(f"  {slug:<24} DOWNLOAD FAILED: {type(e).__name__}: {str(e)[:50]}")

print()
print("  available now:")
for f in sorted(os.listdir(DEST)):
    p = os.path.join(DEST, f)
    print(f"    {f:<32} {os.path.getsize(p)/1048576:6.1f} MB")
PY
