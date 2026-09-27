#!/usr/bin/env bash
# ===========================================================================
# Test the NEW read-scoped token the user just created.
#
# The previous fine-grained token scoped ONLY user:HaaaGemi, so the org's private
# dataset returned 404.  The user then created a token described as
# "read-only access to all your and your orgs resources" -- which should include
# physics-video-lab.  Verify, then list the repo tree so we can see what is already
# there before uploading anything.
#
# The token arrives via $HF_TOKEN (exported by the caller) and is NEVER written to
# the project tree or to Git, per the mentor's rule.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOK="$HF_TOKEN"
if [ -z "$TOK" ]; then echo "  FATAL: HF_TOKEN not set"; exit 1; fi
echo "  token length=${#TOK} prefix=${TOK:0:3}****"
H=(-H "Authorization: Bearer $TOK")

echo
echo "=== whoami ==="
curl -sS -m 30 "${H[@]}" https://huggingface.co/api/whoami-v2 2>/dev/null \
  | "$WS/tools/conda_env/bin/python" -c "
import sys, json
d = json.load(sys.stdin)
print('  user :', d.get('name'), '/', d.get('fullname'))
print('  orgs :', [o['name'] for o in d.get('orgs', [])])
at = d.get('auth',{}).get('accessToken',{})
print('  role :', at.get('role'))
fg = at.get('fineGrained')
if fg:
    print('  global:', fg.get('global'))
    for s in fg.get('scoped', []):
        e = s.get('entity', {})
        print(f\"  scope : {e.get('type')}:{e.get('name')} perms={len(s.get('permissions',[]))}\")
else:
    print('  (classic token - no fine-grained scoping)')
" 2>&1

echo
echo "=== THE DECISIVE TEST: can we read the private dataset now? ==="
printf "  api/datasets/<repo>      -> "
curl -sS -o /tmp/d.json -w '%{http_code} ' -m 40 "${H[@]}" \
  "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets"
head -c 400 /tmp/d.json | tr -d '\n'; echo
printf "  api/datasets?author=org  -> "
curl -sS -o /tmp/l.json -w '%{http_code} ' -m 40 "${H[@]}" \
  "https://huggingface.co/api/datasets?author=physics-video-lab&limit=50"
head -c 400 /tmp/l.json | tr -d '\n'; echo

echo
echo "=== repo TREE (what is already uploaded?) ==="
curl -sS -m 60 "${H[@]}" \
  "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets/tree/main" 2>&1 \
  | head -c 4000
echo

echo
echo "=== README of the dataset repo ==="
curl -sS -m 40 "${H[@]}" \
  "https://huggingface.co/datasets/physics-video-lab/physics-video-assets/raw/main/README.md" 2>&1 | head -60

echo
echo "=== assets_manifest.json (if present) ==="
curl -sS -m 40 "${H[@]}" \
  "https://huggingface.co/datasets/physics-video-lab/physics-video-assets/raw/main/assets_manifest.json" 2>&1 | head -c 2500
