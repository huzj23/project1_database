#!/usr/bin/env bash
# ===========================================================================
# Full inventory of the private HF dataset, so we know exactly what is already
# there before uploading.  The repo is PRIVATE (confirmed: "private":true,
# sha 856c29a84fa2233a9c53928c6727d8e5586a0a2a) and the new read token works.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOK="$HF_TOKEN"
H=(-H "Authorization: Bearer $TOK")
OUT="$WS/tmp/hf_inventory.txt"
: > "$OUT"

{
echo "=== recursive tree of the dataset repo ==="
curl -sS -m 90 "${H[@]}" \
  "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets/tree/main?recursive=true&expand=true" \
  2>/dev/null | "$WS/tools/conda_env/bin/python" -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception as e:
    print('  parse error', e); raise SystemExit
dirs = [x for x in d if x['type']=='directory']
files = [x for x in d if x['type']=='file']
print(f'  directories={len(dirs)} files={len(files)}')
print()
print('  --- DIRECTORIES ---')
for x in sorted(dirs, key=lambda y: y['path']):
    print('   ', x['path'])
print()
print('  --- FILES (path, size) ---')
for x in sorted(files, key=lambda y: y['path']):
    sz = x.get('size') or (x.get('lfs') or {}).get('size') or 0
    print(f\"    {sz:>12,}  {x['path']}\")
" 2>&1

echo
echo "=== assets_manifest.json: which assets are recorded? ==="
curl -sS -m 60 "${H[@]}" \
  "https://huggingface.co/datasets/physics-video-lab/physics-video-assets/raw/main/assets_manifest.json" \
  2>/dev/null | "$WS/tools/conda_env/bin/python" -c "
import sys, json
m = json.load(sys.stdin)
print('  schema_version:', m.get('schema_version'))
print('  repository    :', m.get('repository'))
print('  assets        :', len(m.get('assets', [])))
for a in m.get('assets', []):
    files = a.get('files', [])
    total = sum(f.get('bytes', 0) for f in files)
    print(f\"    - {a.get('id'):40s} kind={a.get('kind'):12s} license={a.get('license'):12s} files={len(files):3d} {total/1e6:8.2f} MB\")
" 2>&1
} >> "$OUT" 2>&1

grep -aE 'directories=|^    - |^   assets|schema_version|repository|assets  ' "$OUT" | head -30 | sed 's/^/  /'
echo "  (full: $OUT)"
