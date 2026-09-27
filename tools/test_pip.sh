#!/usr/bin/env bash
# Focused test: can Blender's bundled python reach the package index?
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== env ==="
echo "SSL_CERT_FILE = ${SSL_CERT_FILE:-<unset>}"
echo "PIP_CERT      = ${PIP_CERT:-<unset>}"
echo "https_proxy   = ${https_proxy:-<unset>}"
echo "PIP_INDEX_URL = ${PIP_INDEX_URL:-<unset>}"
ls -la "$WS/tools/runtime/ca-bundle.crt" 2>/dev/null || echo "CA BUNDLE MISSING"

echo
echo "=== urllib test (with CA) ==="
"$BLENDER_PY" - <<'PY'
import os, ssl, urllib.request
print("cafile env:", os.environ.get("SSL_CERT_FILE"))
for url in ("https://pypi.tuna.tsinghua.edu.cn/simple/",):
    try:
        r = urllib.request.urlopen(url, timeout=30)
        print("OK ", r.status, url)
    except Exception as e:
        print("ERR", type(e).__name__, str(e)[:160])
PY

echo
echo "=== pip install pybullet (real, not dry-run) ==="
"$BLENDER_PY" -m pip install --no-warn-script-location \
  -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" \
  --cert "$SSL_CERT_FILE" \
  pybullet 2>&1 | tail -8

echo
echo "=== import check ==="
"$BLENDER_PY" -c "import pybullet; print('pybullet', pybullet.getAPIVersion())" 2>&1 | tail -2
