#!/usr/bin/env bash
# ===========================================================================
# Additive upload driver.
#
# WHY NOT `sync_hf_assets.py upload` DIRECTLY:
# upload_assets() calls build_remote_manifest(project_root, records, repo_id), which
# rebuilds the manifest from ONLY the selected records and then overwrites the remote
# `assets_manifest.json` wholesale.  The remote manifest currently describes the
# mentor's 11 assets (195 files, 1960.94 MB).  Uploading our 3 assets with the stock
# command would therefore DELETE all 11 of their records -- a destructive side effect
# on someone else's work.
#
# It also overwrites README.md with docs/HUGGINGFACE_DATASET_CARD.md.  That diff is
# purely additive (0 lines removed, 3 added), so it is safe, but the manifest is not.
#
# This driver therefore:
#   1. MERGES the remote manifest with our entries (remote entries preserved verbatim)
#   2. uploads only our 3 asset folders
#   3. uploads the merged manifest
#   4. uploads the (additive) dataset card
#   5. re-reads the remote state to prove the mentor's 11 are still present
#
# The mentor's scripts are NOT modified; this only calls huggingface_hub directly.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"
export HF_TOKEN="${HF_TOKEN:?HF_TOKEN must be exported by the caller}"
export HF_HUB_DISABLE_TELEMETRY=1

DRY="${1:-dry}"

"$PY" - "$DRY" <<'PY' 2>&1 | sed 's/^/  /'
import importlib.util as u, json, os, shutil, sys
from pathlib import Path

DRY = sys.argv[1] != "live"
REPO_ID = "physics-video-lab/physics-video-assets"
OURS = ["special_plush_elephant", "replicad_apartment", "turntable"]

from huggingface_hub import HfApi, hf_hub_download
api = HfApi(endpoint="https://huggingface.co")
root = Path(".").resolve()

# --- load the sync module (do not modify it) -------------------------------
spec = u.spec_from_file_location("syncmod", "scripts/sync_hf_assets.py")
m = u.module_from_spec(spec); sys.modules["syncmod"] = m; spec.loader.exec_module(m)

# --- 1. current remote manifest -------------------------------------------
rem_path = hf_hub_download(repo_id=REPO_ID, filename="assets_manifest.json",
                           repo_type="dataset", force_download=True)
remote = json.load(open(rem_path, encoding="utf-8"))
remote_ids = [a["id"] for a in remote["assets"]]
print(f"remote manifest: {len(remote_ids)} assets: {remote_ids}")

# --- 2. build our entries with the mentor's own function ------------------
recs = {r.asset_id: r for r in m.discover_assets(root)}
ours = []
for aid in OURS:
    r = recs[aid]
    files = [{"path": p.relative_to(root).as_posix(),
              "bytes": p.stat().st_size,
              "sha256": m._sha256(p)} for p in sorted(m._payload_files(r))]
    ours.append({"id": r.asset_id, "kind": r.kind, "license": r.license,
                 "source_page": r.metadata.get("source_page"),
                 "directory": r.relative_directory.as_posix(), "files": files})
    print(f"  ours: {aid}  {len(files)} files  {sum(f['bytes'] for f in files)/1e6:.2f} MB")

# --- 3. MERGE: remote entries win for ids we are not adding ---------------
merged_assets = [a for a in remote["assets"] if a["id"] not in OURS] + ours
merged = dict(remote)
merged["assets"] = merged_assets
merged["repository"] = REPO_ID     # the stale field said TLEphage/...; correct it
merged_ids = [a["id"] for a in merged_assets]

print(f"\nmerged manifest: {len(merged_ids)} assets")
print(f"  preserved from remote: {[i for i in merged_ids if i not in OURS]}")
print(f"  added by us          : {[i for i in merged_ids if i in OURS]}")
missing = [i for i in remote_ids if i not in merged_ids]
if missing:
    raise SystemExit(f"FATAL: merge would drop {missing}")
print("  no remote asset is dropped: OK")

out = Path("/data/raw/huzijian/project1_database/tmp/merged_manifest.json")
out.write_text(json.dumps(merged, indent=2), encoding="utf-8")
print(f"  wrote {out} ({out.stat().st_size:,} bytes)")

if DRY:
    print("\nDRY RUN -- nothing uploaded.")
    for aid in OURS:
        r = recs[aid]
        n = len(m._payload_files(r))
        sz = sum(p.stat().st_size for p in m._payload_files(r))
        print(f"  WOULD UPLOAD {r.relative_directory.as_posix()}  ({n} files, {sz/1e6:.2f} MB)")
    print(f"  WOULD UPLOAD assets_manifest.json ({out.stat().st_size:,} bytes, merged)")
    print("  WOULD UPLOAD README.md (additive card: 0 removed / 3 added lines)")
    raise SystemExit(0)

# --- 4. upload ------------------------------------------------------------
ignore = ["**/.DS_Store", "**/Thumbs.db", "**/*.part", "**/*.blend1",
          "**/*.blend2", "**/*.blend3", "**/__pycache__/**"]
for aid in OURS:
    r = recs[aid]
    print(f"uploading {r.relative_directory.as_posix()} ...")
    api.upload_folder(folder_path=str(r.directory),
                      path_in_repo=r.relative_directory.as_posix(),
                      repo_id=REPO_ID, repo_type="dataset",
                      ignore_patterns=ignore,
                      commit_message=f"Sync asset {aid}")
print("uploading merged manifest ...")
api.upload_file(path_or_fileobj=str(out), path_in_repo="assets_manifest.json",
                repo_id=REPO_ID, repo_type="dataset",
                commit_message="Merge our assets into the checksummed manifest")
print("uploading dataset card ...")
api.upload_file(path_or_fileobj="docs/HUGGINGFACE_DATASET_CARD.md", path_in_repo="README.md",
                repo_id=REPO_ID, repo_type="dataset",
                commit_message="Document the canonical private dataset repository")

# --- 5. prove the result -------------------------------------------------
back = hf_hub_download(repo_id=REPO_ID, filename="assets_manifest.json",
                       repo_type="dataset", force_download=True)
after = json.load(open(back, encoding="utf-8"))
after_ids = [a["id"] for a in after["assets"]]
print(f"\nAFTER: {len(after_ids)} assets")
print(f"  mentor's 11 still present: {all(i in after_ids for i in remote_ids)}")
print(f"  ours present            : {all(i in after_ids for i in OURS)}")
print(f"  ids: {after_ids}")
PY
