#!/usr/bin/env bash
# (1) outdoor ground textures on Poly Haven
# (2) any turntable MODEL (not texture) on Poly Haven
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, urllib.request
def fetch(u):
    r = urllib.request.Request(u, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(r, timeout=60) as f:
        return f.read()

print("=== ground textures ===")
try:
    allt = json.loads(fetch("https://api.polyhaven.com/assets?t=textures"))
    print(f"  total: {len(allt)}")
    groups = {
        "asphalt/road": ["asphalt", "road", "pavement"],
        "grass/lawn":   ["grass", "lawn", "meadow", "moss"],
        "sport/court":  ["court", "turf", "sport", "running", "track"],
        "paving":       ["paving", "cobble", "sidewalk", "brick_floor", "concrete"],
    }
    for label, kws in groups.items():
        hits = sorted(s for s in allt
                      if any(k in s.lower() or
                             k in " ".join(allt[s].get("categories", [])).lower()
                             for k in kws))
        print(f"  [{label:<13}] {', '.join(hits[:12])}")
except Exception as e:
    print("  FAILED:", e)

print()
print("=== models (looking for a turntable / lazy susan) ===")
try:
    allm = json.loads(fetch("https://api.polyhaven.com/assets?t=models"))
    print(f"  total models: {len(allm)}")
    kws = ("turn", "lazy", "sus", "disc", "disk", "plate", "tray", "table", "round")
    hits = sorted(s for s in allm if any(k in s.lower() for k in kws))
    print(f"  matches: {', '.join(hits[:20]) if hits else '(none)'}")
    cats = {}
    for s, m in allm.items():
        for c in m.get("categories", []):
            cats[c] = cats.get(c, 0) + 1
    top = sorted(cats.items(), key=lambda kv: -kv[1])[:12]
    print(f"  categories: {top}")
except Exception as e:
    print("  models API FAILED:", e)
PY
