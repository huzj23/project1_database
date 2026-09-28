#!/usr/bin/env bash
# V5.5 stage 03: probe the server toolchain needed for the remaining stage-03 work
# (contact-sheet generation, and later the render/encode chain).
set -uo pipefail
R=/data/raw/huzijian/project1_database
PY="$R/tools/conda_env/bin/python"

echo "=== ffmpeg ==="
if command -v ffmpeg >/dev/null 2>&1; then
  command -v ffmpeg
  ffmpeg -version 2>/dev/null | head -1
else
  echo "  ffmpeg NOT on PATH"
fi
for c in "$R/tools/runtime/bin/ffmpeg" "$R/tools/runtime_local/ffmpeg" "$R/tools/ffmpeg"; do
  [ -x "$c" ] && echo "  found: $c"
done
find "$R/tools" -maxdepth 3 -name 'ffmpeg*' -type f 2>/dev/null | head -5 | sed 's/^/  candidate: /'

echo
echo "=== python imaging / mesh libs ==="
"$PY" - <<'PY'
import importlib
for name in ("PIL", "numpy", "trimesh", "matplotlib", "pybullet", "scipy"):
    try:
        m = importlib.import_module(name)
        print(f"  {name:12s} OK  {getattr(m, '__version__', 'n/a')}")
    except Exception as exc:
        print(f"  {name:12s} MISSING ({type(exc).__name__})")
PY

echo
echo "=== is there an existing review-image generator? ==="
ls "$R/tools" | grep -iE 'review|contact|sheet|thumb' | sed 's/^/  /'
find "$R" -maxdepth 3 -name '*review*' -o -maxdepth 3 -name '*contact_sheet*' 2>/dev/null | head -5 | sed 's/^/  /'

echo
echo "=== existing review-image size (to match the convention) ==="
"$PY" - <<'PY'
from pathlib import Path
try:
    from PIL import Image
except Exception:
    raise SystemExit("PIL unavailable")
d = Path("/data/raw/huzijian/project1_database/outcomes/v5_asset_review/objects")
pngs = sorted(d.glob("*.png"))
print(f"  {len(pngs)} review images")
for p in pngs[:3]:
    with Image.open(p) as im:
        print(f"    {p.name}: {im.size} {im.mode}")
# Which approved assets lack an image?
want = ["Borage_GLA240Gamma_Tocopherol", "Creatine_Monohydrate",
        "Big_Dot_Aqua_Pencil_Case", "Clue_Board_Game_Classic_Edition"]
have = {p.stem for p in pngs}
for w in want:
    print(f"    {w}: {'image present' if w in have else 'IMAGE MISSING'}")
PY
