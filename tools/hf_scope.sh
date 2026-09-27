#!/usr/bin/env bash
# ===========================================================================
# Show the LOCAL token's full permission scopes.
#
# Result so far: the local token authenticates as HaaaGemi (Hu Zijian), who IS a
# member of org `physics-video-lab` -- so the org exists (the server's token user
# sivenlu is simply not a member, which is why it saw "not found").
#
# But physics-video-lab/physics-video-assets STILL returns "Repository not found"
# with the local token, and the token is `fineGrained` with global permissions only
# ["discussion.write","post.write"].  HF answers 404 (not 403) for repos a token
# cannot read, so the likely cause is a MISSING READ SCOPE rather than a missing repo.
# Print the full scope list to confirm.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOKF="$WS/tmp/localtok.txt"
if [ ! -f "$TOKF" ]; then echo "  FATAL: token file missing"; exit 1; fi
TOK=$(tr -d '\r\n' < "$TOKF")

echo "=== FULL whoami-v2 (pretty) ==="
curl -sS -m 30 -H "Authorization: Bearer $TOK" https://huggingface.co/api/whoami-v2 2>&1 \
  | "$WS/tools/conda_env/bin/python" -c "import sys,json; print(json.dumps(json.load(sys.stdin), indent=2))" 2>&1 \
  | head -60 | sed 's/^/  /'

echo
echo "=== can the token see the ORG at all? ==="
for u in "https://huggingface.co/api/organizations/physics-video-lab" \
         "https://huggingface.co/api/organizations/physics-video-lab/members" \
         "https://huggingface.co/api/datasets?author=physics-video-lab&limit=50"; do
  echo "  --- $u"
  curl -sS -m 30 -H "Authorization: Bearer $TOK" "$u" 2>&1 | head -c 700 | sed 's/^/    /'
  echo
done

rm -f "$TOKF"
echo "  (token deleted from server)"
