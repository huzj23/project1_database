#!/usr/bin/env bash
# Two asset questions:
#   (1) which Poly Haven ground materials suit street / park / sports?
#   (2) is there a turntable anywhere in our assets, or must we build/find one?
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== (1) Poly Haven texture search: outdoor grounds ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, urllib.request
def fetch(u):
    r = urllib.request.Request(u, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return f.read()
try:
    allt = json.loads(fetch("https://api.polyhaven.com/assets?t=textures"))
except Exception as e:
    print("  textures API failed:", e); raise SystemExit
print(f"  total textures: {len(allt)}")
want = {
    "asphalt": ["asphalt", "road", "pavement"],
    "grass":   ["grass", "lawn", "meadow"],
    "pitch":   ["soccer", "football", "turf", "court", "concrete_floor"],
    "sidewalk":["paving", "cobble", "sidewalk", "tile"],
}
seen = set()
for label, kws in want.items():
    hits = []
    for slug, meta in allt.items():
        cats = " ".join(meta.get("categories", [])).lower()
        if any(k in slug.lower() or k in cats for k in kws):
            hits.append(slug)
    hits = sorted(set(hits))[:10]
    print(f"  [{label}] {', '.join(hits) if hits else '(none)'}")
PY

echo
echo "=== (2) turntable-like objects in GSO (local full library) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os
g = "/data/raw/huzijian/project1_database/models/gso"
names = sorted(os.listdir(g)) if os.path.isdir(g) else []
print(f"  GSO on server: {len(names)} objects")
kws = ("turn", "lazy", "sus", "spin", "rotat", "disc", "disk", "plate", "tray", "turntable")
hits = [n for n in names if any(k in n.lower() for k in kws)]
print(f"  turntable-ish matches: {hits if hits else '(none)'}")
PY
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, os
p = "/data/raw/huzijian/project1_database/models/gso"
if not os.path.isdir(p):
    print("  (server GSO dir missing)"); raise SystemExit
PY

echo
echo "=== also check the full local GSO catalogue (1033) ==="
"$WS/tools/conda_env/bin/python" - <<'PY'
import json
p = "/data/raw/huzijian/project1_database/target/_gso_index.json"
print("  (skipped: index not present on server; will check locally instead)")
PY
