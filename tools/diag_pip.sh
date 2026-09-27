#!/usr/bin/env bash
# Diagnose why pip inside Blender's bundled python cannot reach the index.
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== python + ssl ==="
"$BLENDER_PY" - <<'PY'
import sys, ssl, os
print("python :", sys.version.split()[0])
print("ssl    :", ssl.OPENSSL_VERSION)
print("cafile :", ssl.get_default_verify_paths().cafile)
print("capath :", ssl.get_default_verify_paths().capath)
for k in ("https_proxy", "http_proxy", "HTTPS_PROXY"):
    print(f"{k:12}: {os.environ.get(k)}")
import urllib.request
for url in ("https://pypi.tuna.tsinghua.edu.cn/simple/",
            "https://pypi.org/simple/"):
    try:
        r = urllib.request.urlopen(url, timeout=25)
        print("OK ", r.status, url)
    except Exception as e:
        print("ERR", type(e).__name__, str(e)[:120], url)
PY

echo
echo "=== pip version ==="
"$BLENDER_PY" -m pip --version 2>&1 | head -2

echo
echo "=== pip install dry probe (verbose, 1 pkg) ==="
"$BLENDER_PY" -m pip install --no-warn-script-location \
  -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" \
  -v --dry-run "pybullet" 2>&1 | grep -Ei "error|ssl|proxy|Looking|index|cert|url" | head -20
