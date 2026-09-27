#!/usr/bin/env bash
# ===========================================================================
# Two blockers found before upload:
#
#  (1) `turntable` records `license: CC0 (project-generated; no third-party
#      content)`.  The sync script matches licenses by EXACT STRING
#      (`record.license in allowed_licenses`), so a prose licence can never match
#      an allowlist entry -- it is not an SPDX identifier.  The mentor's own CC0
#      assets use the clean id `CC0-1.0`.  Fix: set license to `CC0-1.0` and move
#      the prose into `license_note` (which is what that field is for).
#
#  (2) huggingface_hub is not installed in the conda env, so upload cannot run.
#      Install it (the script's own error message points at `pip install -e ".[assets]"`).
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== (1) survey every asset's license string for SPDX validity ==="
"$PY" - <<'PY'
import glob, re, yaml
SPDX_OK = re.compile(r'^(CC0-1\.0|CC-BY(-SA|-NC|-ND)?-4\.0|CC BY(-SA|-NC|-ND)? 4\.0|MIT|Apache-2\.0|UNKNOWN)$')
for p in sorted(glob.glob("assets/*/*/asset.yaml")):
    m = yaml.safe_load(open(p))
    lic = str(m.get("license"))
    ok = bool(SPDX_OK.match(lic))
    print(f"  {'OK ' if ok else 'BAD'}  {str(m.get('id')):44s} {lic}")
PY

echo
echo "=== fix the turntable manifest ==="
"$PY" - <<'PY'
import re, yaml, pathlib
p = pathlib.Path("assets/objects/turntable/asset.yaml")
t = p.read_text(encoding="utf-8")
if "license: CC0-1.0" in t:
    print("  already fixed")
else:
    if not p.with_suffix(".yaml.pre_lic").exists():
        p.with_suffix(".yaml.pre_lic").write_text(t, encoding="utf-8")
    t2, n = re.subn(r'^license:.*$',
                    'license: CC0-1.0\nlicense_note: project-generated; no third-party content',
                    t, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("FATAL: license line not substituted")
    # drop the old prose license_note if one already existed, to avoid duplicates
    p.write_text(t2, encoding="utf-8")
    print("  license -> CC0-1.0 (+ license_note)")
m = yaml.safe_load(open(p))
print("  now:", m.get("license"), "|", m.get("license_note"))
PY

echo
echo "=== (2) install huggingface_hub ==="
"$PY" -c "import huggingface_hub as h; print('  already installed', h.__version__)" 2>/dev/null || {
  echo "  installing..."
  "$PY" -m pip install --quiet "huggingface_hub>=0.23" 2>&1 | tail -5 | sed 's/^/    /'
}
"$PY" -c "import huggingface_hub as h; print('  huggingface_hub', h.__version__)" 2>&1 | tail -1 | sed 's/^/  /'

echo
echo "=== dry-run: what will be uploaded ==="
"$PY" scripts/sync_hf_assets.py list \
  --asset-id special_plush_elephant --asset-id replicad_apartment --asset-id turntable \
  --allowed-license "CC BY-SA 4.0" --allowed-license "CC BY-NC 4.0" --allowed-license "CC0-1.0" \
  2>&1 | sed 's/^/  /'
