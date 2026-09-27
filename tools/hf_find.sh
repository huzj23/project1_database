#!/usr/bin/env bash
# ===========================================================================
# The token is VALID (whoami -> sivenlu / Siwen Lu) but
#   physics-video-lab/physics-video-assets -> "Repository not found"
# Hugging Face returns 404 (not 403) for repos you cannot see, so this means either
# the org/id is spelled differently, or this account has no access.
#
# Find the real repo: search the Hub, and list the org's / the user's datasets.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOK=$(cat "$HOME/.cache/huggingface/token" 2>/dev/null | tr -d '\r\n')
H=(-H "Authorization: Bearer $TOK")

echo "=== does org 'physics-video-lab' exist? ==="
curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/organizations/physics-video-lab" 2>&1 | head -c 500 | sed 's/^/  /'
echo
curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/users/physics-video-lab/overview" 2>&1 | head -c 400 | sed 's/^/  /'
echo

echo "=== datasets owned by org physics-video-lab ==="
curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/datasets?author=physics-video-lab&limit=50" 2>&1 | head -c 1500 | sed 's/^/  /'
echo

echo "=== datasets owned by the token's user (sivenlu) ==="
curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/datasets?author=sivenlu&limit=50" 2>&1 | head -c 1500 | sed 's/^/  /'
echo

echo "=== SEARCH the Hub for 'physics-video' ==="
curl -sS -m 40 "${H[@]}" "https://huggingface.co/api/datasets?search=physics-video&limit=50" 2>&1 \
  | tr ',' '\n' | grep -iE '"id"|"private"|"downloads"' | head -40 | sed 's/^/  /'
echo

echo "=== SEARCH for 'physics-video-assets' ==="
curl -sS -m 40 "${H[@]}" "https://huggingface.co/api/datasets?search=physics-video-assets&limit=50" 2>&1 | head -c 1500 | sed 's/^/  /'
echo

echo "=== orgs the token's user belongs to ==="
curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/whoami-v2" 2>&1 \
  | tr '{' '\n' | grep -oE '"name":"[^"]+"' | head -20 | sed 's/^/  /'
