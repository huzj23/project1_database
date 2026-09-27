"""Project-owned asset discovery, validation, and file resolution."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Iterable

from physim.config import load_yaml

ASSET_KINDS = ("object", "environment", "material", "hdri")
BLENDER_MESH_EXTENSIONS = frozenset(
    {".blend", ".fbx", ".glb", ".gltf", ".obj", ".wrl", ".x3d"}
)
MATERIAL_EXTENSIONS = frozenset({".blend", ".json", ".mtl"})
HDRI_EXTENSIONS = frozenset({".exr", ".hdr"})
COLLISION_TYPES = frozenset({"none", "sphere", "box", "mesh", "convex_hull", "cylinder"})
PRIMITIVE_OBJECT_CATEGORIES = frozenset({"sphere", "cylinder", "cube", "cone"})
SIMULATION_EXTENSIONS = frozenset({".urdf"})


@dataclass(frozen=True)
class CollisionSpec:
    collision_type: str
    mesh_path: Path | None = None
    simulation_path: Path | None = None
    radius: float | None = None
    bounding_radius: float | None = None
    footprint_radius: float | None = None
    support_height: float | None = None
    center: tuple[float, float, float] | None = None
    half_extents: tuple[float, float, float] | None = None


@dataclass(frozen=True)
class MaterialSpec:
    """A PBR texture set an asset asks the renderer to apply.

    Declared in the asset manifest as::

        visual:
          mesh: visual/model.obj
          material:
            pbr: dark_wood          # Poly Haven set, i.e. <pbr>.blend/textures
            category: wood_textures # sub-directory of the PBR texture root
            uv_scale: 1.6           # uniform scale on the texture mapping node
            textures: visual/textures/dark_wood  # optional asset-local maps

    ``category`` may be omitted, in which case every category under the texture
    root is searched.  ``uv_scale`` defaults to 1.0, i.e. the mesh's own UVs.

    ``textures`` is optional and names a directory RELATIVE TO THE ASSET that holds
    the maps.  When present it is searched before the shared library, which lets an
    asset ship its own material and stay usable after
    ``sync_hf_assets.py download`` on a machine that has no
    ``<workspace>/models/pbr_textures``.

    The spec is deliberately *data*: the manifest says which material an asset
    wants, and the renderer decides how to build it.  An asset with no
    ``visual.material`` block gets ``None`` and renders exactly as before.
    """

    pbr: str
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


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    kind: str
    category: str
    asset_dir: Path
    visual_path: Path | None
    render_import_kwargs: dict[str, Any]
    collision: CollisionSpec
    size: tuple[float, float, float] | None
    scale: tuple[float, float, float]
    mass_range: tuple[float, float]
    friction_range: tuple[float, float]
    restitution_range: tuple[float, float]
    allowed_scenarios: tuple[str, ...]
    metadata: dict[str, Any]
    initial_quaternion: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    #: Optional declarative PBR material (``visual.material``).  Defaults to
    #: None, so every asset that does not declare one is unaffected.
    material: MaterialSpec | None = None

    @property
    def radius(self) -> float:
        radius = (
            self.collision.radius
            if self.collision.collision_type == "sphere"
            else self.collision.footprint_radius or self.collision.bounding_radius
        )
        if radius is None:
            raise ValueError(f"Asset {self.asset_id!r} has no collision bounding radius")
        return radius

    @property
    def support_height(self) -> float:
        height = (
            self.collision.radius
            if self.collision.collision_type == "sphere"
            else self.collision.support_height
        )
        if height is None:
            raise ValueError(f"Asset {self.asset_id!r} has no collision support height")
        return height


class AssetManager:
    """Load asset manifests without exposing registry paths to scenarios."""

    def __init__(self, registry_path: str | Path, asset_root: str | Path):
        self.registry_path = Path(registry_path).resolve()
        self.asset_root = Path(asset_root).resolve()
        registry = load_yaml(self.registry_path)
        if int(registry.get("version", 0)) != 2:
            raise ValueError(f"Unsupported asset registry version in {self.registry_path}")
        self.manifest_name = str(registry.get("manifest", "asset.yaml"))
        configured_roots = registry.get("roots", {})
        self.kind_roots = {
            kind: self._safe_path(self.asset_root, configured_roots[kind])
            for kind in ASSET_KINDS
        }
        self._manifests = self._discover()

    def _safe_path(self, parent: Path, value: str | Path) -> Path:
        path = (parent / value).resolve()
        try:
            path.relative_to(self.asset_root)
        except ValueError as exc:
            raise ValueError(f"Asset path escapes {self.asset_root}: {value}") from exc
        return path

    def _discover(self) -> dict[str, tuple[str, Path, dict[str, Any]]]:
        manifests: dict[str, tuple[str, Path, dict[str, Any]]] = {}
        for kind, root in self.kind_roots.items():
            if not root.exists():
                continue
            for manifest_path in sorted(root.rglob(self.manifest_name)):
                entry = load_yaml(manifest_path)
                asset_id = str(entry.get("id", "")).strip()
                if not asset_id:
                    raise ValueError(f"Missing asset id in {manifest_path}")
                manifest_kind = str(entry.get("kind", "")).strip()
                if manifest_kind != kind:
                    raise ValueError(
                        f"Asset {asset_id!r} has kind {manifest_kind!r}, expected {kind!r}"
                    )
                if asset_id in manifests:
                    raise ValueError(f"Duplicate asset id {asset_id!r} in {manifest_path}")
                manifests[asset_id] = (kind, manifest_path.parent.resolve(), entry)
        return manifests

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._manifests))

    def all(
        self,
        *,
        kind: str | None = None,
        scenario: str | None = None,
        require_files: bool = True,
    ) -> tuple[AssetSpec, ...]:
        return tuple(
            self.get(
                asset_id,
                kind=kind,
                scenario=scenario,
                require_files=require_files,
            )
            for asset_id in self.ids
            if kind is None or self._manifests[asset_id][0] == kind
        )

    def get(
        self,
        asset_id: str,
        *,
        kind: str | None = None,
        scenario: str | None = None,
        require_files: bool = True,
    ) -> AssetSpec:
        try:
            manifest_kind, asset_dir, entry = self._manifests[asset_id]
        except KeyError as exc:
            raise KeyError(f"Unknown asset {asset_id!r}; available: {', '.join(self.ids)}") from exc
        if kind is not None and manifest_kind != kind:
            raise ValueError(
                f"Asset {asset_id!r} has kind {manifest_kind!r}, expected {kind!r}"
            )

        allowed_scenarios = tuple(str(value) for value in entry.get("allowed_scenarios", ()))
        if scenario and "*" not in allowed_scenarios and scenario not in allowed_scenarios:
            raise ValueError(f"Asset {asset_id!r} is not allowed for scenario {scenario!r}")

        visual = dict(entry.get("visual", {}))
        visual_path = self._optional_asset_file(asset_dir, visual.get("mesh"))
        if visual_path is not None:
            extensions = self._extensions_for_kind(manifest_kind)
            if visual_path.suffix.lower() not in extensions:
                supported = ", ".join(sorted(extensions))
                raise ValueError(
                    f"Unsupported {manifest_kind} file {visual_path.name!r}; supported: {supported}"
                )
            if require_files and not visual_path.is_file():
                raise FileNotFoundError(
                    f"Missing asset file {visual_path}; run scripts/fetch_assets.py first"
                )
        elif manifest_kind in ("object", "environment"):
            raise ValueError(f"Asset {asset_id!r} requires visual.mesh")
        render_import_kwargs = dict(visual.get("import_kwargs", {}))
        if (
            manifest_kind in ("object", "environment")
            and visual_path is not None
            and visual_path.suffix.lower() == ".blend"
        ):
            object_name = str(visual.get("object_name", "")).strip()
            if not object_name:
                raise ValueError(
                    f"Asset {asset_id!r} uses .blend and requires visual.object_name"
                )
            object_directory = visual_path / "Object"
            render_import_kwargs.update(
                {
                    "filepath": str(object_directory / object_name),
                    "directory": str(object_directory),
                    "filename": object_name,
                }
            )

        category = str(entry.get("category", "uncategorized"))
        collision_entry = dict(entry.get("collision", {"type": "none"}))
        collision_type = str(collision_entry.get("type", "none"))
        if collision_type not in COLLISION_TYPES:
            raise ValueError(f"Unsupported collision type {collision_type!r} for {asset_id!r}")
        collision_mesh = self._optional_asset_file(asset_dir, collision_entry.get("mesh"))
        simulation_path = self._optional_asset_file(
            asset_dir, collision_entry.get("simulation")
        )
        if collision_type in ("mesh", "convex_hull") and collision_mesh is None:
            raise ValueError(f"Asset {asset_id!r} collision type {collision_type!r} requires mesh")
        if collision_type in ("mesh", "convex_hull") and simulation_path is None:
            raise ValueError(
                f"Asset {asset_id!r} collision type {collision_type!r} requires simulation"
            )
        # A cylinder is a primitive collision shape and, like the sphere, needs no
        # collision mesh -- but PyBullet can only build an EXACT disc from a URDF,
        # so the turntable declares its `simulation` file and no mesh.
        if collision_type == "cylinder" and simulation_path is None:
            raise ValueError(
                f"Asset {asset_id!r} collision type 'cylinder' requires a "
                "URDF simulation file"
            )
        if collision_mesh is not None and collision_mesh.suffix.lower() not in BLENDER_MESH_EXTENSIONS:
            raise ValueError(f"Unsupported collision mesh file {collision_mesh.name!r}")
        if require_files and collision_mesh is not None and not collision_mesh.is_file():
            raise FileNotFoundError(f"Missing collision mesh {collision_mesh}")
        if simulation_path is not None and simulation_path.suffix.lower() not in SIMULATION_EXTENSIONS:
            raise ValueError(f"Unsupported simulation file {simulation_path.name!r}")
        if require_files and simulation_path is not None and not simulation_path.is_file():
            raise FileNotFoundError(f"Missing simulation file {simulation_path}")
        radius = self._optional_float(collision_entry.get("radius"))
        bounding_radius = self._optional_float(collision_entry.get("bounding_radius"))
        footprint_radius = self._optional_float(collision_entry.get("footprint_radius"))
        support_height = self._optional_float(collision_entry.get("support_height"))
        center = self._optional_vector(collision_entry.get("center"))
        half_extents = self._optional_vector(collision_entry.get("half_extents"))
        if collision_type == "sphere" and (radius is None or radius <= 0):
            raise ValueError(f"Asset {asset_id!r} sphere collision requires a positive radius")
        if collision_type == "box" and (center is None or half_extents is None):
            raise ValueError(f"Asset {asset_id!r} box collision requires center and half_extents")
        if collision_type in ("mesh", "convex_hull") and (
            bounding_radius is None
            or bounding_radius <= 0
            or support_height is None
            or support_height <= 0
        ):
            raise ValueError(
                f"Asset {asset_id!r} mesh collision requires positive "
                "bounding_radius and support_height"
            )
        if footprint_radius is not None and (
            footprint_radius <= 0
            or (bounding_radius is not None and footprint_radius > bounding_radius)
        ):
            raise ValueError(
                f"Asset {asset_id!r} footprint_radius must be positive and no larger "
                "than bounding_radius"
            )
        if (
            manifest_kind == "object"
            and category not in PRIMITIVE_OBJECT_CATEGORIES
            and collision_type not in ("mesh", "convex_hull")
        ):
            raise ValueError(
                f"Non-primitive object {asset_id!r} in category {category!r} "
                "requires a low-poly mesh or convex_hull collision"
            )

        physics = dict(entry.get("physics", {}))
        orientation = dict(entry.get("initial_orientation", {}))
        return AssetSpec(
            asset_id=asset_id,
            kind=manifest_kind,
            category=category,
            asset_dir=asset_dir,
            visual_path=visual_path,
            render_import_kwargs=render_import_kwargs,
            collision=CollisionSpec(
                collision_type=collision_type,
                mesh_path=collision_mesh,
                simulation_path=simulation_path,
                radius=radius,
                bounding_radius=bounding_radius,
                footprint_radius=footprint_radius,
                support_height=support_height,
                center=center,
                half_extents=half_extents,
            ),
            size=self._optional_vector(visual.get("size")),
            scale=self._vector(visual.get("scale", (1.0, 1.0, 1.0)), "visual.scale"),
            mass_range=self._range(physics.get("mass_range", (0.0, 0.0)), "mass_range"),
            friction_range=self._range(
                physics.get("friction_range", (0.0, 0.0)), "friction_range"
            ),
            restitution_range=self._range(
                physics.get("restitution_range", (0.0, 0.0)), "restitution_range"
            ),
            allowed_scenarios=allowed_scenarios,
            metadata=dict(entry),
            initial_quaternion=self._quaternion(
                orientation.get("quaternion_wxyz", (1.0, 0.0, 0.0, 0.0)),
                asset_id,
            ),
            material=self._material(visual.get("material"), asset_id, asset_dir),
        )

    @staticmethod
    def _material(
        value: Any, asset_id: str, asset_dir: Path | None = None
    ) -> MaterialSpec | None:
        """Parse the optional ``visual.material`` block.

        Absent/empty means "no material" and yields None.  A malformed block is
        an error rather than a silent fallback to grey, because a manifest that
        asks for a material and does not get one is exactly the bug this exists
        to prevent.
        """
        if value in (None, ""):
            return None
        if not isinstance(value, dict):
            raise ValueError(
                f"Asset {asset_id!r} visual.material must be a mapping with a "
                "'pbr' key"
            )
        pbr = str(value.get("pbr", "")).strip()
        if not pbr:
            raise ValueError(f"Asset {asset_id!r} visual.material requires 'pbr'")
        category = value.get("category")
        category = None if category in (None, "") else str(category).strip()
        uv_scale = float(value.get("uv_scale", 1.0))
        if uv_scale <= 0.0:
            raise ValueError(
                f"Asset {asset_id!r} visual.material.uv_scale must be positive"
            )
        textures = value.get("textures")
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
        )

    def _optional_asset_file(self, asset_dir: Path, value: Any) -> Path | None:
        if value in (None, ""):
            return None
        path = (asset_dir / str(value)).resolve()
        try:
            path.relative_to(asset_dir)
        except ValueError as exc:
            raise ValueError(f"Asset file escapes {asset_dir}: {value}") from exc
        return path

    @staticmethod
    def _extensions_for_kind(kind: str) -> frozenset[str]:
        if kind in ("object", "environment"):
            return BLENDER_MESH_EXTENSIONS
        if kind == "material":
            return MATERIAL_EXTENSIONS
        return HDRI_EXTENSIONS

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return None if value is None else float(value)

    @classmethod
    def _optional_vector(cls, value: Any) -> tuple[float, float, float] | None:
        return None if value is None else cls._vector(value, "vector")

    @staticmethod
    def _vector(value: Iterable[Any], field: str) -> tuple[float, float, float]:
        result = tuple(float(item) for item in value)
        if len(result) != 3:
            raise ValueError(f"{field} must contain three numbers")
        return result

    @staticmethod
    def _range(value: Iterable[Any], field: str) -> tuple[float, float]:
        result = tuple(float(item) for item in value)
        if len(result) != 2 or result[0] > result[1]:
            raise ValueError(f"{field} must be an ordered [min, max] pair")
        return result

    @staticmethod
    def _quaternion(
        value: Iterable[Any], asset_id: str
    ) -> tuple[float, float, float, float]:
        result = tuple(float(item) for item in value)
        if len(result) != 4:
            raise ValueError(
                f"initial_orientation.quaternion_wxyz for {asset_id!r} needs 4 values"
            )
        norm = math.sqrt(sum(item * item for item in result))
        if norm <= 1e-12:
            raise ValueError(f"Initial quaternion for {asset_id!r} cannot be zero")
        return tuple(item / norm for item in result)
