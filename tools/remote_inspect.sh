#!/usr/bin/env bash
# ===========================================================================
# READ-ONLY inspection of the remote repo before we change anything.
#
# The token is passed ONLY through the environment of this one command; it is never
# written into the project tree, a YAML profile, or shell history.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
export HF_TOKEN="${HF_TOKEN:?HF_TOKEN must be exported by the caller}"
export HF_HUB_DISABLE_TELEMETRY=1

"$PY" - <<'PY' 2>&1 | sed 's/^/  /'
import os, json, io
from huggingface_hub import HfApi, hf_hub_download

api = HfApi(endpoint="https://huggingface.co")
REPO = "physics-video-lab/physics-video-assets"

info = api.repo_info(repo_id=REPO, repo_type="dataset")
print(f"repo        : {info.id}")
print(f"private     : {info.private}")
print(f"sha         : {info.sha}")
print(f"lastModified: {info.lastModified}")

files = api.list_repo_files(repo_id=REPO, repo_type="dataset")
print(f"\ntotal files at repo root+tree: {len(files)}")
tops = sorted({f.split('/')[0] for f in files})
print(f"top-level entries ({len(tops)}):")
for t in tops:
    print(f"    {t}")

print("\n--- the two files the upload WOULD overwrite ---")
for name in ("README.md", "assets_manifest.json"):
    try:
        p = hf_hub_download(repo_id=REPO, filename=name, repo_type="dataset",
                            force_download=True)
        sz = os.path.getsize(p)
        print(f"\n{name}: {sz:,} bytes  -> {p}")
        if name.endswith(".json"):
            d = json.load(open(p))
            print(f"   schema_version: {d.get('schema_version')}")
            print(f"   repository    : {d.get('repository')}")
            ids = [a['id'] for a in d.get('assets', [])]
            print(f"   assets ({len(ids)}): {ids}")
        else:
            txt = open(p, encoding="utf-8").read()
            print("   --- first 25 lines ---")
            for ln in txt.splitlines()[:25]:
                print(f"   | {ln}")
    except Exception as e:
        print(f"\n{name}: ERROR {type(e).__name__}: {e}")
PY
