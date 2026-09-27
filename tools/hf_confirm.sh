#!/usr/bin/env bash
# ===========================================================================
# Confirm the exact reason the dataset is unreachable.
#
# The local token (HaaaGemi / Hu Zijian) is a FINE-GRAINED token whose `scoped`
# permissions cover ONLY the entity user:HaaaGemi.  There is NO entry for the org
# physics-video-lab.  HF returns 404 for repos a token cannot read, which is exactly
# what we observe.
#
# Test what the token CAN see, to separate "no permission" from "repo absent".
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOKF="$WS/tmp/localtok.txt"
TOK=$(tr -d '\r\n' < "$TOKF" 2>/dev/null)
PY="$WS/tools/conda_env/bin/python"

echo "=== scoped entities in the token ==="
curl -sS -m 30 -H "Authorization: Bearer $TOK" https://huggingface.co/api/whoami-v2 2>/dev/null \
  | "$PY" -c "
import sys, json
d = json.load(sys.stdin)
fg = d.get('auth',{}).get('accessToken',{}).get('fineGrained',{})
print('  role       :', d.get('auth',{}).get('accessToken',{}).get('role'))
print('  global     :', fg.get('global'))
print('  scoped entities:')
for s in fg.get('scoped', []):
    e = s.get('entity', {})
    print(f\"    - {e.get('type')}:{e.get('name')}  perms={len(s.get('permissions',[]))}\")
print('  orgs       :', [o['name'] for o in d.get('orgs',[])])
"

echo
echo "=== is the org itself visible? ==="
for u in "organizations/physics-video-lab" \
         "organizations/physics-video-lab/members" \
         "datasets?author=physics-video-lab&limit=50"; do
  printf "  %-46s -> " "$u"
  curl -sS -o /tmp/o.json -w '%{http_code} ' -m 30 -H "Authorization: Bearer $TOK" "https://huggingface.co/api/$u"
  head -c 200 /tmp/o.json | tr -d '\n'
  echo
done

echo
echo "=== the user's OWN datasets (should work if scope is user-only) ==="
curl -sS -m 30 -H "Authorization: Bearer $TOK" \
  "https://huggingface.co/api/datasets?author=HaaaGemi&limit=50" 2>/dev/null \
  | tr ',' '\n' | grep -oE '"id":"[^"]*"' | sed 's/^/  /' || echo "  (none)"

echo
echo "=== raw README fetch with the token ==="
curl -sS -o /tmp/r.txt -w '  http=%{http_code}\n' -m 30 -H "Authorization: Bearer $TOK" \
  "https://huggingface.co/datasets/physics-video-lab/physics-video-assets/raw/main/README.md"
head -c 300 /tmp/r.txt | sed 's/^/  /'

rm -f "$TOKF"
echo
echo "  (token deleted from server)"
