#!/usr/bin/env bash
# The vendored phyco-sim on the server is its OWN git checkout.  A git revision +
# working-tree diff is the correct, compact backup of it (01 section 6).
WS=/data/raw/huzijian/project1_database
V="$WS/code/vendor/phyco-sim"
OUT="$WS/outcomes/v55/bootstrap/20260928T194500"
mkdir -p "$OUT"
cd "$V" || exit 1

echo "=== vendor repo identity ==="
git rev-parse HEAD 2>&1 | sed 's/^/  HEAD: /'
git rev-parse --abbrev-ref HEAD 2>&1 | sed 's/^/  branch: /'
git remote -v 2>&1 | head -2 | sed 's/^/  /'
echo "  describe: $(git describe --always --dirty 2>&1)"
echo "  last commit: $(git log -1 --format='%H %ad %s' --date=short 2>&1)"

echo
echo "=== uncommitted changes (the project-specific patches, if any) ==="
CHANGED=$(git status --porcelain 2>&1)
if [ -z "$CHANGED" ]; then
  echo "  working tree CLEAN -- no local patches"
else
  echo "$CHANGED" | head -30 | sed 's/^/  /'
  echo "  (total $(echo "$CHANGED" | wc -l) entries)"
fi

echo
echo "=== saving a full patch + tracked-file list as the backup ==="
git diff HEAD > "$OUT/vendor_phyco_sim_working_tree.patch" 2>&1
echo "  patch bytes: $(stat -c%s "$OUT/vendor_phyco_sim_working_tree.patch")"
git ls-files > "$OUT/vendor_phyco_sim_tracked_files.txt" 2>&1
echo "  tracked files: $(wc -l < "$OUT/vendor_phyco_sim_tracked_files.txt")"
git rev-parse HEAD > "$OUT/vendor_phyco_sim_HEAD.txt" 2>&1

echo
echo "=== is the diff against LOCAL just a different commit? ==="
echo "  server HEAD: $(git rev-parse HEAD)"
echo "  (compare with the local vendor HEAD below)"
