#!/usr/bin/env bash
# ===========================================================================
# Make a declared PBR material resolvable from INSIDE the asset directory.
#
# Problem: the turntable declares `visual.material: {pbr: dark_wood}`, which
# materials.py resolves against the shared library at
# <workspace>/models/pbr_textures (623 MB, deliberately OUTSIDE the repository).
# A teammate who clones the repo and runs `sync_hf_assets.py download` would NOT have
# those textures, so `apply_declared_material` raises FileNotFoundError and the asset
# is unusable -- which contradicts the requirement that the asset be usable after
# download ("后面直接用就行了").
#
# Fix, in the same declarative spirit as the existing design:
#   1. MaterialSpec gains `textures`: an optional directory RELATIVE to the asset,
#      holding the maps for this material.
#   2. The loader resolves it against the asset directory (and rejects escapes).
#   3. find_texture_dir() searches the asset-local directory FIRST, then falls back
#      to the shared root, so existing behaviour for every other asset is unchanged.
#   4. The three dark_wood 4k maps are copied into the turntable asset.
#
# The mentor's scripts are NOT touched; only our own material module, our own loader
# field, and our own turntable asset.
# ===========================================================================
set -uo pipefail
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1
PY="$WS/tools/conda_env/bin/python"

echo "=== 0. back up the files we are about to change ==="
for f in src/physim/assets/__init__.py src/physim/render/materials.py; do
  cp -n "$f" "$f.pre_localtex" 2>/dev/null && echo "  backed up $f" || echo "  (backup exists) $f"
done

echo
echo "=== 1. patch MaterialSpec: add `textures` ==="
"$PY" - <<'PY'
import pathlib
p = pathlib.Path("src/physim/assets/__init__.py")
t = p.read_text(encoding="utf-8")

old = '''    pbr: str
    category: str | None = None
    uv_scale: float = 1.0
'''
new = '''    pbr: str
    category: str | None = None
    uv_scale: float = 1.0
    #: Optional directory holding this material's maps, relative to the asset
    #: directory (for example ``visual/textures/dark_wood``).  When present it is
    #: searched BEFORE the shared PBR library, which is what makes an asset
    #: self-contained: after ``sync_hf_assets.py download`` the maps ship with the
    #: asset instead of relying on <workspace>/models/pbr_textures.
    textures: str | None = None
    #: Absolute directory of the asset that declared this material.  Filled by the
    #: loader so the renderer can resolve ``textures`` without being told which
    #: asset it is drawing.
    asset_dir: str | None = None
'''
if "textures: str | None = None" in t:
    print("  MaterialSpec already patched")
else:
    assert t.count(old) == 1, f"expected 1 match, got {t.count(old)}"
    p.write_text(t.replace(old, new), encoding="utf-8")
    print("  MaterialSpec patched")
PY

echo
echo "=== 2. patch _material(): parse `textures`, resolve against asset_dir ==="
"$PY" - <<'PY'
import pathlib
p = pathlib.Path("src/physim/assets/__init__.py")
t = p.read_text(encoding="utf-8")

old_sig = '''    def _material(value: Any, asset_id: str) -> MaterialSpec | None:'''
new_sig = '''    def _material(
        value: Any, asset_id: str, asset_dir: Path | None = None
    ) -> MaterialSpec | None:'''
assert t.count(old_sig) == 1, "signature not unique"
t = t.replace(old_sig, new_sig)

old_ret = '''        return MaterialSpec(pbr=pbr, category=category, uv_scale=uv_scale)'''
new_ret = '''        textures = value.get("textures")
        textures = None if textures in (None, "") else str(textures).strip()
        resolved_dir: str | None = None
        if asset_dir is not None:
            resolved_dir = str(asset_dir)
            if textures:
                candidate = (asset_dir / textures).resolve()
                try:
                    candidate.relative_to(asset_dir)
                except ValueError as exc:
                    raise ValueError(
                        f"Asset {asset_id!r} visual.material.textures escapes "
                        f"{asset_dir}: {textures}"
                    ) from exc
                if not candidate.is_dir():
                    raise ValueError(
                        f"Asset {asset_id!r} visual.material.textures points at a "
                        f"missing directory: {textures}"
                    )
        return MaterialSpec(
            pbr=pbr,
            category=category,
            uv_scale=uv_scale,
            textures=textures,
            asset_dir=resolved_dir,
        )'''
assert t.count(old_ret) == 1, "return not unique"
t = t.replace(old_ret, new_ret)

old_call = '''            material=self._material(visual.get("material"), asset_id),'''
new_call = '''            material=self._material(visual.get("material"), asset_id, asset_dir),'''
assert t.count(old_call) == 1, "call site not unique"
t = t.replace(old_call, new_call)

p.write_text(t, encoding="utf-8")
print("  _material patched (signature, parsing, call site)")
PY

echo
echo "=== 3. patch find_texture_dir(): asset-local first ==="
"$PY" - <<'PY'
import pathlib
p = pathlib.Path("src/physim/render/materials.py")
t = p.read_text(encoding="utf-8")

old = '''def find_texture_dir(
    project_root: str | Path, pbr: str, category: str | None = None
) -> Path | None:
    """Return ``<root>/<category>/<pbr>.blend/textures`` if it exists."""
    root = resolve_pbr_root(project_root)
    categories = [category] if category else _subdirectories(root)
    for name in categories:
        candidate = root / str(name) / f"{pbr}.blend" / "textures"
        if candidate.is_dir():
            return candidate
    return None
'''
new = '''def find_texture_dir(
    project_root: str | Path,
    pbr: str,
    category: str | None = None,
    spec: MaterialSpec | None = None,
) -> Path | None:
    """Return the directory holding ``pbr``'s maps, or None.

    Search order:

    1. the asset-local directory declared by ``visual.material.textures`` (so an
       asset can ship its own maps and stay usable after an HF download);
    2. ``<shared root>/<category>/<pbr>.blend/textures``.

    ``spec`` is optional so the existing two/three-argument callers keep working.
    """
    if spec is not None and spec.textures and spec.asset_dir:
        candidate = Path(spec.asset_dir) / spec.textures
        if candidate.is_dir():
            return candidate
    root = resolve_pbr_root(project_root)
    categories = [category] if category else _subdirectories(root)
    for name in categories:
        candidate = root / str(name) / f"{pbr}.blend" / "textures"
        if candidate.is_dir():
            return candidate
    return None
'''
assert t.count(old) == 1, "find_texture_dir not unique"
t = t.replace(old, new)

old2 = '''    texture_dir = find_texture_dir(project_root, spec.pbr, spec.category)'''
new2 = '''    texture_dir = find_texture_dir(project_root, spec.pbr, spec.category, spec)'''
assert t.count(old2) == 1, "call not unique"
t = t.replace(old2, new2)

# the error message should mention the asset-local option too
old3 = '''        f"  expected at  : {expected}\\n"'''
new3 = '''        f"  expected at  : {expected}\\n"
        f"  asset-local  : {spec.textures!r} relative to {spec.asset_dir!r}\\n"'''
if old3 in t:
    t = t.replace(old3, new3, 1)
    print("  error message extended")

p.write_text(t, encoding="utf-8")
print("  find_texture_dir + apply_declared_material patched")
PY

echo
echo "=== 4. copy the dark_wood maps into the turntable asset ==="
SRC="$WS/models/pbr_textures/wood_textures/dark_wood.blend/textures"
DST="assets/objects/turntable/visual/textures/dark_wood"
mkdir -p "$DST"
for f in dark_wood_diff_4k.jpg dark_wood_rough_4k.jpg dark_wood_nor_gl_4k.jpg; do
  cp -n "$SRC/$f" "$DST/$f" && echo "  copied $f" || echo "  exists $f"
done
ls -la "$DST" | sed 's/^/  /'
du -sh "$DST" | sed 's/^/  total: /'

echo
echo "=== 5. declare it in the turntable manifest ==="
"$PY" - <<'PY'
import re, pathlib, yaml
p = pathlib.Path("assets/objects/turntable/asset.yaml")
t = p.read_text(encoding="utf-8")
if "textures:" in t:
    print("  already declared")
else:
    old = "    uv_scale: 1.6\n"
    new = ("    uv_scale: 1.6\n"
           "    # Asset-local map directory (relative to this asset).  Searched\n"
           "    # BEFORE the shared library, so the disc renders correctly after\n"
           "    # `sync_hf_assets.py download` without <workspace>/models/pbr_textures.\n"
           "    textures: visual/textures/dark_wood\n")
    assert t.count(old) == 1, f"uv_scale line not unique ({t.count(old)})"
    p.write_text(t.replace(old, new), encoding="utf-8")
    print("  declared textures: visual/textures/dark_wood")
d = yaml.safe_load(open(p))
print("  material block:", d["visual"]["material"])
PY
