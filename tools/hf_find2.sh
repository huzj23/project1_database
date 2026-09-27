#!/usr/bin/env bash
# ===========================================================================
# `physics-video-lab` does not exist as an HF org or user, and searching
# "physics-video-assets" returns nothing.  So the URL in the request does not
# resolve.  Before reporting that, search exhaustively: alternate spellings,
# models as well as datasets, and the token user's own repos.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
TOK=$(cat "$HOME/.cache/huggingface/token" 2>/dev/null | tr -d '\r\n')
H=(-H "Authorization: Bearer $TOK")

echo "=== broad dataset searches ==="
for q in physics-video-lab physics_video phyco physics-video-sim physicsvideo videolab; do
  n=$(curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/datasets?search=$q&limit=100" 2>/dev/null \
      | grep -o '"id"' | wc -l)
  echo "  search '$q' -> $n hits"
  curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/datasets?search=$q&limit=100" 2>/dev/null \
    | tr ',' '\n' | grep -oE '"id":"[^"]*"' | head -6 | sed 's/^/      /'
done

echo
echo "=== same for models ==="
for q in physics-video-lab physics-video-sim phyco; do
  echo "  search '$q':"
  curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/models?search=$q&limit=20" 2>/dev/null \
    | tr ',' '\n' | grep -oE '"id":"[^"]*"' | head -5 | sed 's/^/      /'
done

echo
echo "=== direct probes of plausible ids (with token) ==="
for id in \
  "physics-video-lab/physics-video-assets" \
  "physics-video-lab/physics-video-sim" \
  "physicsvideolab/physics-video-assets" \
  "physics-video/physics-video-assets" \
  "sivenlu/physics-video-assets" ; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' -m 25 "${H[@]}" "https://huggingface.co/api/datasets/$id")
  echo "  $code  $id"
done

echo
echo "=== whoami orgs (full) ==="
curl -sS -m 30 "${H[@]}" "https://huggingface.co/api/whoami-v2" 2>/dev/null \
  | tr ',' '\n' | grep -oE '"name":"[^"]*"' | sed 's/^/  /'
