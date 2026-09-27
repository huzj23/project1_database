#!/usr/bin/env bash
# ===========================================================================
# Can the SERVER reach Hugging Face?
#
# The local Windows box has POISONED DNS for huggingface.co: it resolves to
# 108.160.167.30 (a Dropbox address) and an IPv6 in Meta's 2a03:2880::/32 range.
# Neither is HF, which is why downloads fail locally.  The server fetched the GSO
# assets from the internet earlier, so test it here instead.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh

echo "=== DNS on the server ==="
getent hosts huggingface.co || echo "  getent: FAIL"
getent hosts cdn-lfs.huggingface.co || echo "  getent cdn-lfs: FAIL"

echo
echo "=== plain HTTPS to HF ==="
curl -sS -I -m 30 https://huggingface.co 2>&1 | head -6 | sed 's/^/  /'

echo
echo "=== dataset API: does the repo exist and what is in it? ==="
curl -sS -m 40 "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets" \
  2>&1 | head -c 2000 | sed 's/^/  /'
echo

echo
echo "=== tree listing (top level) ==="
curl -sS -m 40 "https://huggingface.co/api/datasets/physics-video-lab/physics-video-assets/tree/main" \
  2>&1 | head -c 2500 | sed 's/^/  /'
echo

echo
echo "=== is huggingface_hub available in the conda env? ==="
"$PY" -c "import importlib.util as u; print('  hf_hub:', bool(u.find_spec('huggingface_hub')))" 2>&1
"$PY" -c "import importlib.util as u; print('  hf_transfer:', bool(u.find_spec('hf_transfer')))" 2>&1
"$PY" -m pip --version 2>&1 | head -2 | sed 's/^/  /'
