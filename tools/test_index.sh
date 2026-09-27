#!/usr/bin/env bash
# Which index + User-Agent combination can Blender's python actually reach
# through this host's proxy?
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== curl (baseline, known-good) ==="
curl -s -o /dev/null -w '  tuna via curl : %{http_code}\n' --max-time 20 https://pypi.tuna.tsinghua.edu.cn/simple/
curl -s -o /dev/null -w '  pypi via curl : %{http_code}\n' --max-time 20 https://pypi.org/simple/

echo
echo "=== python urllib, several UAs / hosts ==="
"$BLENDER_PY" - <<'PY'
import urllib.request, os
UALIST = [
    ("python-default", None),
    ("pip", "pip/22.2.2"),
    ("browser", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"),
    ("curl", "curl/7.29.0"),
]
URLS = [
    "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "https://pypi.org/simple/",
    "https://mirrors.aliyun.com/pypi/simple/",
]
for url in URLS:
    for name, ua in UALIST:
        req = urllib.request.Request(url)
        if ua:
            req.add_header("User-Agent", ua)
        try:
            r = urllib.request.urlopen(req, timeout=20)
            print(f"  {r.status}  {name:14} {url}")
        except Exception as e:
            code = getattr(e, "code", None)
            print(f"  {code or type(e).__name__:>4}  {name:14} {url}")
PY
