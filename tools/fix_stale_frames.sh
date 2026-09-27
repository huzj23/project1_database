#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# FIX: stale frames in a persistent scratch directory were being re-read.
#
# pipeline.py builds the renderer with
#     scratch_dir = cache_root / <scenario> / seed-<seed> / <variant>
# which is the SAME path every time that seed+variant is rendered.  Kubric writes
# per-frame EXRs into that directory and then reads them back; any EXRs left by an
# earlier attempt are picked up too.  That is why:
#   * we asked for 16 frames and got 32 back (16 new + 16 stale), and
#   * changing the camera appeared to have no effect -- half of every output was
#     rendered with the PREVIOUS camera.
#
# Fix: clear the frame artefacts in the scratch directory before rendering.  This
# is project-side code (src/physim/...), not third_party/.
# ---------------------------------------------------------------------------
set -uo pipefail
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
REPO="$WS/code/physics-video-sim/physics-video-sim-main"

"$PY" - "$REPO" <<'PY'
import sys, pathlib, re
repo = pathlib.Path(sys.argv[1])
p = repo / "src/physim/render/blender_backend.py"
t = p.read_text()

if "purge_stale_frames" in t:
    print("  already patched")
else:
    helper = '''

def purge_stale_frames(scratch_dir: str | Path) -> int:
    """Delete leftover frame files so a re-run cannot read a previous run's frames.

    pipeline.py derives the scratch directory from scenario/seed/variant, so it is
    reused verbatim whenever the same sample is rendered again.  Kubric writes
    frame EXRs there and reads the whole directory back, which silently mixes old
    frames into the new clip (we saw 16 requested -> 32 returned, half of them
    rendered with the previous camera).
    """
    removed = 0
    root = Path(scratch_dir)
    for sub in ("images", "exr", ""):
        d = root / sub if sub else root
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() in (".exr", ".png") and f.name.startswith(("frame_", "rgba_", "depth_", "segmentation_")):
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass
    return removed

'''
    t = t.replace("class PhyCoBlenderBackend", helper.lstrip("\n") + "\nclass PhyCoBlenderBackend", 1)
    # call it at the top of build_scene's body
    m = re.search(r"(    def build_scene\(\s*\n(?:.*\n)*?    \) -> BuiltBlenderScene:\n)", t)
    if m:
        t = t[:m.end()] + (
            '        _purged = purge_stale_frames(self.scratch_dir)\n'
            '        if _purged:\n'
            '            import sys as _sys\n'
            '            print(f"DIAG purged {_purged} stale frame files from {self.scratch_dir}",\n'
            '                  file=_sys.stderr, flush=True)\n'
        ) + t[m.end():]
        p.write_text(t)
        print("  patched build_scene to purge stale frames")
    else:
        print("  !! could not locate build_scene signature")
PY

echo
echo "=== verify: clean run should now yield exactly 16 frames ==="
BL="$WS/tools/runtime/blender-3.4.1-linux-x64/blender"
cd "$REPO" || exit 1
rm -rf "$REPO/datasets/free_fall"
"$BL" --background --factory-startup --python scripts/generate.py -- \
  --config configs/server.yaml --seed 1000 --variant x0.5 > "$WS/log/diag2.log" 2>&1
echo "  exit code: $?"
grep -E '^DIAG' "$WS/log/diag2.log" | sed 's/^/  /'
echo
D="$REPO/datasets/free_fall/seed-001000/x0.5"
for sub in rgb depth segmentation; do
  printf '  %-14s %s frames\n' "$sub" "$(ls "$D/$sub" 2>/dev/null | wc -l)"
done
