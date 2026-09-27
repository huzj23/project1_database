#!/usr/bin/env bash
# Install loguru (the "misc" group aborted on pandas before reaching it) and
# re-run the full import verification.
source /data/raw/huzijian/project1_database/tools/server_env.sh

PY="$WS/tools/conda_env/bin/python"
"$PY" -m pip install --no-warn-script-location --only-binary=:all: \
  --retries 5 --timeout 60 \
  -i "$PIP_INDEX_URL" --trusted-host "$PIP_TRUSTED_HOST" \
  --cert "$SSL_CERT_FILE" loguru 2>&1 | tail -2

echo
echo "=== final verification ==="
"$PY" - <<'PY'
import sys
print("python   ", sys.version.split()[0])
mods = ["numpy", "pybullet", "OpenEXR", "cv2", "trimesh", "pandas",
        "tensorflow", "skimage", "imageio", "png", "loguru", "zstandard"]
bad = []
for m in mods:
    try:
        mod = __import__(m)
        print(f"  {m:12}", getattr(mod, "__version__", "ok"))
    except Exception as e:
        print(f"  {m:12} FAILED: {type(e).__name__}: {e}")
        bad.append(m)
try:
    import bpy
    print("  bpy         ", bpy.app.version_string)
except Exception as e:
    print("  bpy          FAILED:", e); bad.append("bpy")
print("RESULT:", "ALL OK" if not bad else f"MISSING {bad}")
PY

echo
echo "=== env size (must all be inside the workspace) ==="
du -sh "$WS/tools/conda_env" "$WS/tools/conda_pkgs" "$WS/tools/wheels" 2>/dev/null
