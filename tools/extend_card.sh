#!/usr/bin/env bash
# ===========================================================================
# Extend the dataset card so it documents OUR three assets as well as the mentor's.
#
# Matching is done on ASCII-only anchors because the file contains non-ASCII dashes;
# reading/writing is explicit UTF-8.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

cp -n docs/HUGGINGFACE_DATASET_CARD.md docs/HUGGINGFACE_DATASET_CARD.md.pre_ours 2>/dev/null || true

"$PY" - <<'PY'
import pathlib
p = pathlib.Path("docs/HUGGINGFACE_DATASET_CARD.md")
t = p.read_text(encoding="utf-8")

# --- 1. extend the "Included assets" list ---------------------------------
anchor = "- `food_lychee`"
if "special_plush_elephant" in t:
    print("  card already documents our assets")
else:
    i = t.index(anchor)
    eol = t.index("\n", i) + 1
    block = (
        "\n"
        "Additional assets contributed by the group (normalized to the same\n"
        "conventions: `source/` original, `visual/`, low-poly `collision/`,\n"
        "`asset.yaml`, `license/`):\n"
        "\n"
        "- `special_plush_elephant` - GSO Sootheze Cold Therapy Elephant, "
        "CC BY-SA 4.0 (attribution + ShareAlike);\n"
        "- `replicad_apartment` - ReplicaCAD/FRL apartment stage, CC BY-NC 4.0 "
        "(attribution, NON-COMMERCIAL only);\n"
        "- `turntable` - project-generated disc, CC0-1.0.\n"
        "\n"
        "`special_plush_elephant` and `replicad_apartment` are NOT CC0-1.0, so they\n"
        "must be named explicitly when uploading:\n"
        "\n"
        "```bash\n"
        "python scripts/sync_hf_assets.py upload \\\n"
        '  --asset-id special_plush_elephant --allowed-license "CC BY-SA 4.0" \\\n'
        '  --asset-id replicad_apartment    --allowed-license "CC BY-NC 4.0" \\\n'
        '  --asset-id turntable             --allowed-license "CC0-1.0"\n'
        "```\n"
        "\n"
        "The `CC BY-NC 4.0` environment must not be used commercially. Assets whose\n"
        "license is `UNKNOWN` remain private-only and are never upload-allowlisted.\n"
    )
    t = t[:eol] + block + t[eol:]

    # --- 2. document the self-contained material convention ---------------
    anchor2 = "The license in each `asset.yaml` and `license/SOURCE.md` applies"
    j = t.index(anchor2)
    note = (
        "An object asset may declare `visual.material` to ask the renderer for a PBR\n"
        "texture set. When it does, the maps can be shipped INSIDE the asset under\n"
        "`visual/textures/<name>/` and referenced with a `textures:` key, which is\n"
        "searched before the shared library. That keeps the asset usable after a plain\n"
        "`download`, with no `<workspace>/models/pbr_textures` present.\n"
        "\n"
    )
    t = t[:j] + note + t[j:]
    p.write_text(t, encoding="utf-8")
    print("  card extended")

print(f"  card now {len(t)} chars, {len(t.splitlines())} lines")
PY

echo
echo "=== resulting card ==="
cat docs/HUGGINGFACE_DATASET_CARD.md | sed 's/^/  | /'
