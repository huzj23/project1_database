#!/usr/bin/env bash
# ===========================================================================
# Test whether the LOCAL Windows HF token can reach the private dataset repo.
#
# Background: the SERVER's token authenticates as "sivenlu" but
# physics-video-lab/physics-video-assets returns "Repository not found" for it.
# The local box has its own token (C:\Users\12447\.cache\huggingface\token) which may
# belong to an account that IS a member of the physics-video-lab org.
#
# Local DNS for huggingface.co is POISONED (resolves to 108.160.167.30, a Dropbox
# address), so all Hub traffic must go through this server, which has a working
# proxy at 127.0.0.1:7890.
#
# The token is uploaded to tmp/, used, then deleted. It is never echoed.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOKF="$WS/tmp/localtok.txt"

if [ ! -f "$TOKF" ]; then echo "  FATAL: $TOKF missing"; exit 1; fi
TOK=$(tr -d '\r\n' < "$TOKF")
echo "=== token identity ==="
echo "  local token length=${#TOK} prefix=${TOK:0:3}****"
md5sum "$TOKF" 2>/dev/null | awk '{print "  local  file md5:", $1}'
md5sum "$HOME/.cache/huggingface/token" 2>/dev/null | awk '{print "  server file md5:", $1}'

echo
echo "=== whoami with the LOCAL token ==="
curl -sS -m 30 -H "Authorization: Bearer $TOK" https://huggingface.co/api/whoami-v2 2>&1 \
  | head -c 700 | sed 's/^/  /'
echo

echo
echo "=== repo lookup with the LOCAL token ==="
curl -sS -m 40 -H "Authorization: Bearer $TOK" \
  "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets" 2>&1 \
  | head -c 2000 | sed 's/^/  /'
echo

echo
echo "=== repo tree with the LOCAL token ==="
curl -sS -m 40 -H "Authorization: Bearer $TOK" \
  "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets/tree/main" 2>&1 \
  | head -c 3000 | sed 's/^/  /'
echo

echo
echo "=== org membership with the LOCAL token ==="
curl -sS -m 30 -H "Authorization: Bearer $TOK" https://huggingface.co/api/whoami-v2 2>&1 \
  | tr ',' '\n' | grep -oE '"name":"[^"]*"' | sed 's/^/  /'

rm -f "$TOKF"
echo
echo "  (token file deleted from the server)"
