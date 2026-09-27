"""Declarative PBR materials for rendered assets.

An asset manifest may ask for a Poly Haven texture set to be applied to its
visual mesh::

    visual:
      mesh: visual/model.obj
      material:
        pbr: dark_wood
        category: wood_textures
        uv_scale: 1.6
        textures: visual/textures/dark_wood   # optional, asset-local

Lookup order for the maps is: the asset-local ``textures`` directory first (so an
asset can carry its own material and remain usable after an HF download), then the
shared library at ``<workspace>/models/pbr_textures``.

The manifest only *declares* the material; :func:`apply_declared_material` is
what turns that declaration into a Blender node tree, and the renderer is the
only caller.  Keeping the split means an asset never has to know about ``bpy``
and the renderer never has to know which asset wants which look.

Why this module exists
----------------------
The turntable disc is a plain OBJ with an empty ``model.mtl``, so before this
existed it rendered as Blender's default grey (measured disc pixels R/B 0.99,
R/G 0.99) instead of the project's frozen ``dark_wood`` (R/B ~1.99, R/G ~1.67).
Writing the material into the MTL was tried and rejected by measurement (R/B
4.04, R/G 2.55 -- far too red); the look only reproduces with a full Principled
node tree, which is what this module builds.

The logic is adapted from ``code/scenarios/phyco_backdrops.py`` (our own
project code, but it lives OUTSIDE this repository, so the pipeline must not
import it).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from physim.assets import MaterialSpec

#: Environment variable that overrides where PBR texture sets are looked up.
PBR_ROOT_ENV_VAR = "PHYSIM_PBR_TEXTURE_ROOT"

#: Default texture root, relative to the project root (the directory that holds
#: ``assets/``, ``configs/`` and ``src/``).  The texture sets are downloaded
#: *outside* the repository, at ``<workspace>/models/pbr_textures``, next to
#: ``<workspace>/code/physics-video-sim/physics-video-sim-main``.
DEFAULT_PBR_ROOT_RELPATH = Path("..") / ".." / ".." / "models" / "pbr_textures"

#: Filename fragments identifying each map in a texture directory.  Matched
#: case-insensitively against the file name.
_MAP_PATTERNS: dict[str, tuple[str, ...]] = {
    "diffuse": ("_diff_", "diffuse", "_col_", "_basecolor_", "_albedo_"),
    "roughness": ("_rough_", "roughness"),
    "normal": ("_nor_gl_", "_nor_dx_", "_nor_", "normal"),
    "displacement": ("_disp_", "displacement", "_height_"),
}


def resolve_pbr_root(project_root: str | Path) -> Path:
    """Locate the directory that holds ``<category>/<pbr>.blend/textures``.

    Order of precedence:

    1. ``$PHYSIM_PBR_TEXTURE_ROOT`` (absolute, or relative to ``project_root``);
    2. the default ``<project_root>/../../../models/pbr_textures``.

    ``project_root`` may be the repository root *or* any directory inside it --
    the renderer passes its ``phyco_sim_root`` (``third_party/phyco-sim``), so
    the value is first normalised to the nearest ancestor that looks like the
    project root (holds both ``assets`` and ``configs``).

    Unlike the asset manager, this deliberately does *not* clamp the result to
    the repository: the texture library is shared project data that lives beside
    the repository, and hard-coding it inside would be worse.
    """
    override = os.environ.get(PBR_ROOT_ENV_VAR)
    if override:
        root = Path(override)
        if not root.is_absolute():
            root = Path(project_root) / root
        return root.resolve()
    base = project_root_for(project_root)
    return (base / DEFAULT_PBR_ROOT_RELPATH).resolve()


def project_root_for(start: str | Path) -> Path:
    """Best-effort project root: nearest ancestor holding ``assets``+``configs``.

    Falls back to ``start`` itself when no such ancestor exists, so a caller
    that already passes a real project root is unaffected.
    """
    path = Path(start).resolve()
    for candidate in (path, *path.parents):
        if (candidate / "assets").is_dir() and (candidate / "configs").is_dir():
            return candidate
    return path


def find_texture_dir(
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


def _subdirectories(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir())


def _find_map(texture_dir: Path, patterns: tuple[str, ...]) -> Path | None:
    for path in sorted(texture_dir.iterdir()):
        if not path.is_file():
            continue
        lowered = path.name.lower()
        if any(pattern in lowered for pattern in patterns):
            return path
    return None


def missing_material_message(
    spec: MaterialSpec, project_root: str | Path
) -> str:
    """Explain exactly what was looked for and how to fix it."""
    root = resolve_pbr_root(project_root)
    expected = root / str(spec.category or "<category>") / f"{spec.pbr}.blend" / "textures"
    return (
        f"PBR material {spec.pbr!r} (category {spec.category!r}) not found.\n"
        f"  looked under : {root}\n"
        f"  expected at  : {expected}\n"
        f"  asset-local  : {spec.textures!r} relative to {spec.asset_dir!r}\n"
        f"  override with: {PBR_ROOT_ENV_VAR}=/path/to/pbr_textures"
    )


def apply_declared_material(
    blender_object: Any,
    spec: MaterialSpec,
    project_root: str | Path,
) -> dict[str, Any]:
    """Attach the declared PBR texture set to an already-added Blender object.

    Kubric's ``PhysicalObject.material`` trait only accepts a Kubric
    ``Material``, so a hand-built node material cannot be passed at construction
    time; the object is added first and its material slots are written here.

    Returns a diagnostics dict (recorded in ``RENDER_DIAGNOSTICS``).  Raises
    ``FileNotFoundError`` when the texture set is missing: silently falling back
    to grey is precisely the bug this exists to remove.
    """
    import bpy

    # Resolve the texture set FIRST: a missing material is the more common and
    # more actionable failure, and it should not be masked by an argument check.
    texture_dir = find_texture_dir(project_root, spec.pbr, spec.category, spec)
    if texture_dir is None:
        raise FileNotFoundError(missing_material_message(spec, project_root))

    if blender_object is None or not hasattr(blender_object, "data"):
        raise TypeError(
            f"Cannot apply material {spec.pbr!r}: {blender_object!r} is not a "
            "Blender mesh object"
        )

    material = bpy.data.materials.new(name=f"pbr_{spec.pbr}")
    material.use_nodes = True
    nodes = material.node_tree
    bsdf = nodes.nodes.get("Principled BSDF")
    info: dict[str, Any] = {
        "pbr": spec.pbr,
        "category": spec.category,
        "uv_scale": spec.uv_scale,
        "texture_dir": str(texture_dir),
        "maps": {},
    }
    if bsdf is None:
        raise RuntimeError(
            f"Principled BSDF node missing from new material for {spec.pbr!r}"
        )

    def add_image(path: Path, non_color: bool = False):
        node = nodes.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(path), check_existing=True)
        node.image.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
        node.interpolation = "Linear"
        return node

    mapping = None
    if spec.uv_scale != 1.0:
        coordinates = nodes.nodes.new("ShaderNodeTexCoord")
        mapping = nodes.nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (
            spec.uv_scale,
            spec.uv_scale,
            spec.uv_scale,
        )
        nodes.links.new(coordinates.outputs["UV"], mapping.inputs["Vector"])

    def wire_uv(node) -> None:
        """Route the (optionally rescaled) UVs into an image node's Vector input."""
        if mapping is not None:
            nodes.links.new(mapping.outputs["Vector"], node.inputs["Vector"])

    found = {
        name: _find_map(texture_dir, patterns)
        for name, patterns in _MAP_PATTERNS.items()
    }

    if found["diffuse"] is not None:
        node = add_image(found["diffuse"])
        wire_uv(node)
        nodes.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
        info["maps"]["diffuse"] = found["diffuse"].name

    if found["roughness"] is not None:
        node = add_image(found["roughness"], non_color=True)
        wire_uv(node)
        nodes.links.new(node.outputs["Color"], bsdf.inputs["Roughness"])
        info["maps"]["roughness"] = found["roughness"].name

    if found["normal"] is not None:
        node = add_image(found["normal"], non_color=True)
        normal_map = nodes.nodes.new("ShaderNodeNormalMap")
        wire_uv(node)
        nodes.links.new(node.outputs["Color"], normal_map.inputs["Color"])
        if "Normal" in bsdf.inputs:
            nodes.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
        info["maps"]["normal"] = found["normal"].name

    # Blender 4.x renamed "Specular" to "Specular IOR Level"; support both.
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.3
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = 0.3

    if not info["maps"]:
        raise FileNotFoundError(
            f"PBR material {spec.pbr!r} has a texture directory ({texture_dir}) "
            "but no diffuse/roughness/normal map was recognised in it"
        )

    if not hasattr(blender_object.data, "materials"):
        raise TypeError(
            f"Cannot apply material {spec.pbr!r}: {blender_object.name!r} has no "
            "material slots"
        )
    if blender_object.data.materials:
        blender_object.data.materials[0] = material
    else:
        blender_object.data.materials.append(material)

    info["applied_to"] = str(getattr(blender_object, "name", "<unnamed>"))
    info["uv_layer_count"] = len(getattr(blender_object.data, "uv_layers", ()))
    return info
