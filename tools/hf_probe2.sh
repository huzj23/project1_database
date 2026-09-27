#!/usr/bin/env bash
# ===========================================================================
# The server CAN reach huggingface.co (HTTP 200, via a CONNECT proxy), but the
# dataset API returns {"error":"Invalid username or password."}.  Distinguish:
#   (a) repo is private/gated -> needs a token;
#   (b) the proxy is intercepting and the API needs auth;
#   (c) wrong repo id.
# Also try to read the repo's README (which the user says documents upload/download).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"

echo "=== proxy env on the server ==="
env | grep -iE 'proxy|HF_|HUGGING' | sed 's/^/  /' || echo "  (none in env)"

echo
echo "=== is it a proxy?  show the CONNECT chain ==="
curl -sS -v -o /dev/null -m 25 https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets 2>&1 \
  | grep -iE 'connect|proxy|http/|< ' | head -12 | sed 's/^/  /'

echo
echo "=== does the repo page exist publicly? (HTML) ==="
curl -sS -o /tmp/hfpage.html -w "  http_code=%{http_code} size=%{size_download}\n" -m 30 \
  "https://huggingface.co/datasets/physics-video-lab/physics-video-assets"
grep -oiE '(private|gated|not found|404|repository)' /tmp/hfpage.html 2>/dev/null | sort | uniq -c | head -6 | sed 's/^/  /'

echo
echo "=== try the README raw endpoints ==="
for u in \
  "https://huggingface.co/datasets/physics-video-lab/physics-video-assets/raw/main/README.md" \
  "https://huggingface.co/datasets/physics-video-lab/physics-video-assets/resolve/main/README.md" ; do
  echo "  --- $u"
  curl -sS -m 30 -w "  http=%{http_code}\n" "$u" 2>&1 | head -30 | sed 's/^/    /'
done

echo
echo "=== token present anywhere on the server? ==="
for f in "$HOME/.cache/huggingface/token" "$HOME/.huggingface/token" "$WS/.hf_token"; do
  [ -f "$f" ] && echo "  FOUND $f" || echo "  absent $f"
done
env | grep -c 'HF_TOKEN\|HUGGING_FACE_HUB_TOKEN' | sed 's/^/  HF token env vars: /'

echo
echo "=== python hf availability ==="
"$PY" -c "import importlib.util as u; print('  hf_hub:', bool(u.find_spec('huggingface_hub')))" 2>&1
"$PY" -c "import importlib.util as u; print('  datasets:', bool(u.find_spec('datasets')))" 2>&1
