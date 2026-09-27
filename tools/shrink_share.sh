#!/usr/bin/env bash
# ===========================================================================
# Shrink the contact sheets to JPEG and package the archive.
#
# The PNG contact sheets are 9.3 MB of the 43 MB, and they are only preview aids, so
# re-encoding them as JPEG q88 cuts them dramatically and buys headroom under the
# 50 MB cap.  Videos and physics annotations are left byte-identical -- they are the
# actual deliverable.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
SHARE="$WS/share_build"

echo "=== before ==="
du -sh "$SHARE/contact_sheets" | sed 's/^/  /'

"$WS/tools/conda_env/bin/python" -u - <<'PY'
import glob, os
from PIL import Image
d = "/data/raw/huzijian/project1_database/share_build/contact_sheets"
tot = 0
for p in sorted(glob.glob(d + "/*.png")):
    im = Image.open(p).convert("RGB")
    jp = p[:-4] + ".jpg"
    im.save(jp, quality=88, optimize=True)
    os.remove(p)
    tot += os.path.getsize(jp)
print(f"  {len(glob.glob(d+'/*.jpg'))} sheets -> {tot/1e6:.2f} MB (was PNG)")
PY

echo "=== after ==="
du -sh "$SHARE/contact_sheets" | sed 's/^/  /'
du -sh "$SHARE" | sed 's/^/  TOTAL: /'

echo
echo "=== copy the README in ==="
cp "$WS/share/README.md" "$SHARE/README.md" 2>/dev/null || echo "  README not staged at $WS/share/README.md"
ls -la "$SHARE/README.md" 2>/dev/null | sed 's/^/  /'
du -sh "$SHARE" | sed 's/^/  TOTAL with README: /'

echo
echo "=== directory tree ==="
find "$SHARE" -maxdepth 2 -type d | sort | sed "s|$SHARE|  .|"
echo "  --- file counts ---"
echo "    videos:         $(find $SHARE/videos -name '*.mp4' | wc -l)"
echo "    annotations:    $(find $SHARE/annotations -type f | wc -l) files in $(find $SHARE/annotations -mindepth 2 -maxdepth 2 -type d | wc -l) dirs"
echo "    contact sheets: $(find $SHARE/contact_sheets -type f | wc -l)"
