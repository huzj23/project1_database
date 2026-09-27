#!/usr/bin/env bash
# Probe which asset hosts the server can reach directly.
# Downloading server-side is ~10x faster than pushing over SFTP.
source /data/raw/huzijian/project1_database/tools/server_env.sh

probe() {
  printf '  %-72s ' "$1"
  curl -s -o /dev/null -w '%{http_code}\n' --max-time 25 "$1" || echo ERR
}

echo "=== asset host reachability ==="
probe "https://huggingface.co"
probe "https://huggingface.co/api/datasets/ai-habitat/ReplicaCAD_dataset"
probe "https://api.polyhaven.com/files/studio_small_09"
probe "https://storage.googleapis.com/kubric-public/assets/GSO/GSO.json"
probe "https://storage.googleapis.com/kubric-public/assets/HDRI_haven/HDRI_haven.json"

echo
echo "=== ReplicaCAD repo file list (HF API) ==="
curl -s --max-time 40 "https://huggingface.co/api/datasets/ai-habitat/ReplicaCAD_dataset" |
  head -c 400
echo
echo "--- tree ---"
curl -s --max-time 40 "https://huggingface.co/api/datasets/ai-habitat/ReplicaCAD_dataset/tree/main" |
  head -c 1200
echo
echo "=== GSO manifest sample ==="
curl -s --max-time 40 "https://storage.googleapis.com/kubric-public/assets/GSO/GSO.json" |
  python3 -c "import sys,json; d=json.load(sys.stdin); a=d['assets']; k=list(a)[:3]; print('assets:',len(a)); [print(' ',n,a[n]['kwargs'].get('render_filename')) for n in k]" 2>/dev/null || echo "  (parse skipped)"
