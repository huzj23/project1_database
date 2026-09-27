#!/usr/bin/env bash
# Find and fetch a dark hardwood (mahogany-like) texture for the turntable disc.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
"$WS/tools/conda_env/bin/python" - <<'PY'
import json, urllib.request, os
def fetch(u, t=120):
    r = urllib.request.Request(u, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(r, timeout=t) as f:
        return f.read()

allt = json.loads(fetch("https://api.polyhaven.com/assets?t=textures"))
kw = ("wood", "mahogany", "walnut", "oak", "plank", "timber")
hits = sorted(s for s in allt
              if any(k in s.lower() or k in " ".join(allt[s].get("categories", [])).lower()
                     for k in kw))
print("wood candidates:")
for h in hits:
    print("   ", h)
PY
