#!/usr/bin/env bash
# ===========================================================================
# My licence fix inserted a `license_note:` while the file ALREADY had one, so the
# manifest now carries a duplicate key (YAML silently keeps the last).  Remove the
# one I added and keep the file's own, then re-verify.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== current head of turntable/asset.yaml ==="
head -14 assets/objects/turntable/asset.yaml | cat -n | sed 's/^/  /'

echo
echo "=== duplicate-key count ==="
grep -c '^license_note:' assets/objects/turntable/asset.yaml | sed 's/^/  license_note lines: /'
grep -c '^license:' assets/objects/turntable/asset.yaml | sed 's/^/  license lines: /'

echo
echo "=== repair: keep exactly one license_note, in the provenance block ==="
"$PY" - <<'PY'
import pathlib, yaml
p = pathlib.Path("assets/objects/turntable/asset.yaml")
lines = p.read_text(encoding="utf-8").splitlines()
out, seen_lic, seen_note = [], False, False
for ln in lines:
    if ln.startswith("license:"):
        if seen_lic:
            continue
        seen_lic = True
        out.append("license: CC0-1.0")
        continue
    if ln.startswith("license_note:"):
        if seen_note:
            continue          # drop the duplicate I introduced
        seen_note = True
    out.append(ln)
p.write_text("\n".join(out) + "\n", encoding="utf-8")
m = yaml.safe_load(open(p))
print("  license      :", m.get("license"))
print("  license_note :", m.get("license_note"))
print("  id           :", m.get("id"), "| category:", m.get("category"))
PY

echo
echo "=== final head ==="
head -14 assets/objects/turntable/asset.yaml | cat -n | sed 's/^/  /'

echo
echo "=== does everything still load? ==="
"$PY" -c "
import sys; sys.path.insert(0,'src')
from physim.assets import AssetManager
am = AssetManager('configs/assets.yaml','assets')
a = am.get('turntable')
print('  turntable OK: r=', a.collision.radius if hasattr(a.collision,'radius') else 'n/a', 'br=', a.collision.bounding_radius)
" 2>&1 | sed 's/^/  /'

echo
echo "=== dry-run again (all three) ==="
"$PY" scripts/sync_hf_assets.py list \
  --asset-id special_plush_elephant --asset-id replicad_apartment --asset-id turntable \
  --allowed-license "CC BY-SA 4.0" --allowed-license "CC BY-NC 4.0" --allowed-license "CC0-1.0" \
  2>&1 | sed 's/^/  /'
