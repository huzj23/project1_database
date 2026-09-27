#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Fetch the "interactive background" asset sets directly on the server.
#
#   B1  ReplicaCAD interactive   -> models/backgrounds/replicad/   (HF, CC BY-NC 4.0)
#   B3  GSO object subset        -> models/gso/                    (GCS, CC BY-SA 4.0)
#
# Server-side download is ~10x faster than pushing from the local machine
# (measured: 1.5+ MB/s here vs ~0.17 MB/s over SFTP).
#
# Usage:
#   bash tools/fetch_interactive_assets.sh            # default subset
#   GSO_N=250 bash tools/fetch_interactive_assets.sh  # larger subset
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh

PY="$WS/tools/conda_env/bin/python"
BG="$WS/models/backgrounds"
GSODIR="$WS/models/gso"
GSO_N="${GSO_N:-140}"
mkdir -p "$BG" "$GSODIR"

# ---------------------------------------------------------------------------
echo "=================== B1  ReplicaCAD interactive ==================="
# ---------------------------------------------------------------------------
if [ -d "$BG/replicad/stages" ] && [ -n "$(ls -A "$BG/replicad/stages" 2>/dev/null)" ]; then
  echo "already present: $BG/replicad"
else
  rm -rf "$BG/replicad" "$BG/replicad_interactive.tar.gz" "$BG/replicad_tmp"
  cd "$BG" || exit 1
  # NOTE: the server ships git 1.8.3, which supports neither --filter nor
  # --sparse, so a plain shallow clone is the only option. The repo is ~150 MB.
  git clone --depth 1 \
      https://huggingface.co/datasets/ai-habitat/ReplicaCAD_dataset replicad \
    || { echo "clone FAILED"; exit 1; }
  rm -rf replicad/.git
fi
echo "stages : $(ls "$BG/replicad/stages" 2>/dev/null | wc -l)"
echo "objects: $(ls "$BG/replicad/objects" 2>/dev/null | wc -l)"
echo "urdf   : $(ls "$BG/replicad/urdf" 2>/dev/null | wc -l)"
cp -f "$BG/replicad/LICENSE.txt" "$BG/replicad/LICENSE.txt" 2>/dev/null || true
du -sh "$BG/replicad" 2>/dev/null | sed 's/^/  /'

# ---------------------------------------------------------------------------
echo
echo "=================== B3  GSO subset (n=$GSO_N) ==================="
# ---------------------------------------------------------------------------
"$PY" - "$GSODIR" "$GSO_N" <<'PY'
import json, os, sys, tarfile, urllib.request, io, random
gso_dir, n_want = sys.argv[1], int(sys.argv[2])
BASE = "https://storage.googleapis.com/kubric-public/assets/GSO"
MANIFEST = f"{BASE}/GSO.json"

def fetch(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout)

print("  loading GSO manifest ...")
with fetch(MANIFEST, 120) as r:
    man = json.load(r)
assets = man["assets"]
print(f"  manifest assets: {len(assets)}")

# balance the pick across categories, preferring smaller objects so the
# transfer and the render both stay cheap
by_cat = {}
for name, a in assets.items():
    cat = (a.get("metadata") or {}).get("category") or "Uncategorised"
    by_cat.setdefault(cat, []).append(name)
cats = sorted(by_cat, key=lambda c: -len(by_cat[c]))
random.seed(20260921)
for c in cats:
    random.shuffle(by_cat[c])

picked, i = [], 0
while len(picked) < n_want and any(by_cat[c] for c in cats):
    c = cats[i % len(cats)]
    if by_cat[c]:
        picked.append((by_cat[c].pop(), c))
    i += 1
print(f"  picked {len(picked)} objects across {len({c for _, c in picked})} categories")

ok = skip = fail = 0
for idx, (name, cat) in enumerate(picked, 1):
    dest = os.path.join(gso_dir, name)
    if os.path.isfile(os.path.join(dest, "object.urdf")):
        ok += 1
        continue
    os.makedirs(dest, exist_ok=True)
    try:
        with fetch(f"{BASE}/{name}.tar.gz", 600) as r:
            blob = r.read()
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            for m in tf.getmembers():
                base = os.path.basename(m.name)
                if not base or not m.isfile():
                    continue
                if base.endswith((".obj", ".urdf", ".mtl", ".json", ".png")):
                    m.name = base
                    tf.extract(m, dest, filter="data")
        ok += 1
        if idx % 20 == 0:
            print(f"    [{idx}/{len(picked)}] {name} ({cat})", flush=True)
    except Exception as e:
        fail += 1
        print(f"    ! {name}: {type(e).__name__}: {e}")

print(f"  GSO objects ready: {ok}   failed: {fail}   (skipped existing counted in ok)")
PY
echo "  gso objects: $(find "$GSODIR" -name 'object.urdf' 2>/dev/null | wc -l)"
du -sh "$GSODIR" 2>/dev/null | sed 's/^/  /'

# ---------------------------------------------------------------------------
echo
echo "=================== result ==================="
# ---------------------------------------------------------------------------
df -h "$WS" | tail -1 | sed 's/^/  /'
du -sh "$WS/models" 2>/dev/null | sed 's/^/  /'
