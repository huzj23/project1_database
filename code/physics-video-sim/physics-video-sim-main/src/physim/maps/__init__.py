"""Map registry and semantic surface definitions."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from physim.assets import AssetManager
from physim.config import load_yaml


@dataclass(frozen=True)
class SurfaceSpec:
    surface_id: str
    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    bounds_xy: tuple[float, float, float, float]
    metadata: dict[str, Any]
    surface_type: str = "horizontal"
    object_extent_range: tuple[float, float] = (0.0, float("inf"))
    polygon_xy: tuple[tuple[float, float], ...] | None = None
    collision_mesh_path: Path | None = None
    collision_simulation_path: Path | None = None

    def supports_object_extent(self, extent: float) -> bool:
        return self.object_extent_range[0] <= extent <= self.object_extent_range[1]

    def contains_xy(self, x: float, y: float, margin: float = 0.0) -> bool:
        """Return whether a circular footprint fits on this surface."""
        xmin, xmax, ymin, ymax = self.bounds_xy
        if not (xmin + margin <= x <= xmax - margin):
            return False
        if not (ymin + margin <= y <= ymax - margin):
            return False
        if self.polygon_xy is None:
            return True

        polygon = self.polygon_xy
        inside = False
        previous = polygon[-1]
        for current in polygon:
            x1, y1 = previous
            x2, y2 = current
            if (y1 > y) != (y2 > y):
                edge_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
                if x < edge_x:
                    inside = not inside
            previous = current
        if not inside:
            return False
        if margin <= 0:
            return True
        return all(
            self._point_segment_distance(x, y, *start, *end) >= margin
            for start, end in zip(polygon, polygon[1:] + polygon[:1])
        )

    @staticmethod
    def _point_segment_distance(
        x: float,
        y: float,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> float:
        dx = x2 - x1
        dy = y2 - y1
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            return math.hypot(x - x1, y - y1)
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length_squared))
        return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


@dataclass(frozen=True)
class MapSpec:
    map_id: str
    environment_asset_id: str
    visual_path: Path
    visual_scale: tuple[float, float, float]
    render_import_kwargs: dict[str, Any]
    collision_center: tuple[float, float, float]
    collision_half_extents: tuple[float, float, float]
    surfaces: tuple[SurfaceSpec, ...]
    metadata: dict[str, Any]

    def surface(self, surface_id: str) -> SurfaceSpec:
        try:
            return next(item for item in self.surfaces if item.surface_id == surface_id)
        except StopIteration as exc:
            raise KeyError(
                f"Unknown surface {surface_id!r} for map {self.map_id!r}"
            ) from exc


class MapManager:
    """Attach map surface semantics to an environment from AssetManager."""

    def __init__(self, registry_path: str | Path, asset_manager: AssetManager):
        self.registry_path = Path(registry_path)
        self.asset_manager = asset_manager
        self.registry = load_yaml(self.registry_path)["maps"]

    def get(
        self,
        map_id: str,
        *,
        scenario: str | None = None,
        require_files: bool = True,
    ) -> MapSpec:
        entry = dict(self.registry[map_id])
        environment_asset_id = str(entry["environment_asset_id"])
        environment = self.asset_manager.get(
            environment_asset_id,
            kind="environment",
            scenario=scenario,
            require_files=require_files,
        )
        if environment.visual_path is None:
            raise ValueError(f"Environment {environment_asset_id!r} has no visual mesh")
        collision = environment.collision
        if (
            collision.collision_type != "box"
            or collision.center is None
            or collision.half_extents is None
        ):
            raise ValueError(
                f"Map {map_id!r} currently requires an environment with box collision"
            )
        surface_entries = self._surface_entries(entry)
        surfaces = tuple(
            self._surface_spec(item, environment.asset_dir, require_files)
            for item in surface_entries
        )
        metadata = dict(environment.metadata)
        metadata["map"] = entry
        return MapSpec(
            map_id=map_id,
            environment_asset_id=environment_asset_id,
            visual_path=environment.visual_path,
            visual_scale=environment.scale,
            render_import_kwargs=environment.render_import_kwargs,
            collision_center=collision.center,
            collision_half_extents=collision.half_extents,
            surfaces=surfaces,
            metadata=metadata,
        )

    @staticmethod
    def _surface_entries(entry: dict[str, Any]) -> list[dict[str, Any]]:
        if "surface_groups" not in entry:
            return [dict(item) for item in entry["surfaces"]]

        entries: list[dict[str, Any]] = []
        for group in entry["surface_groups"]:
            group = dict(group)
            regions = group.pop("regions")
            for region in regions:
                merged = {**group, **dict(region)}
                merged["surface_id"] = str(
                    merged.pop("region_id", merged.get("surface_id", ""))
                )
                if not merged["surface_id"]:
                    raise ValueError("Map surface region requires region_id or surface_id")
                if merged.get("cleanliness") != "verified_clear":
                    raise ValueError(
                        f"Map surface region {merged['surface_id']!r} must be "
                        "marked cleanliness: verified_clear before sampling"
                    )
                entries.append(merged)
        return entries

    @staticmethod
    def _surface_spec(
        item: dict[str, Any],
        environment_dir: Path | None = None,
        require_files: bool = True,
    ) -> SurfaceSpec:
        object_extent_range = item.get(
            "object_extent_range_m", item.get("object_extent_range", (0.0, float("inf")))
        )
        if len(object_extent_range) != 2:
            raise ValueError("object_extent_range_m must contain [min, max]")
        extent_range = tuple(float(value) for value in object_extent_range)
        if extent_range[0] < 0 or extent_range[0] > extent_range[1]:
            raise ValueError("object_extent_range_m must be ordered and non-negative")
        bounds_xy = tuple(float(value) for value in item["bounds_xy"])
        if len(bounds_xy) != 4 or bounds_xy[0] >= bounds_xy[1] or bounds_xy[2] >= bounds_xy[3]:
            raise ValueError(f"Invalid bounds_xy for surface {item['surface_id']!r}")
        polygon_entry = item.get("polygon_xy")
        polygon_xy = None
        if polygon_entry is not None:
            polygon_xy = tuple(
                tuple(float(value) for value in point) for point in polygon_entry
            )
            if len(polygon_xy) < 3 or any(len(point) != 2 for point in polygon_xy):
                raise ValueError(
                    f"polygon_xy for surface {item['surface_id']!r} needs at least 3 XY points"
                )

        collision_entry = dict(item.get("collision", {}))
        collision_type = str(collision_entry.get("type", "box"))
        collision_mesh_path = None
        collision_simulation_path = None
        if collision_type == "mesh":
            if environment_dir is None:
                raise ValueError("A mesh surface collision requires an environment directory")
            for key in ("mesh", "simulation"):
                if not collision_entry.get(key):
                    raise ValueError(
                        f"Mesh collision for surface {item['surface_id']!r} requires {key}"
                    )
            collision_mesh_path = MapManager._environment_file(
                environment_dir, collision_entry["mesh"]
            )
            collision_simulation_path = MapManager._environment_file(
                environment_dir, collision_entry["simulation"]
            )
            if require_files and not collision_mesh_path.is_file():
                raise FileNotFoundError(f"Missing surface collision mesh {collision_mesh_path}")
            if require_files and not collision_simulation_path.is_file():
                raise FileNotFoundError(
                    f"Missing surface collision simulation {collision_simulation_path}"
                )
        elif collision_type != "box":
            raise ValueError(
                f"Unsupported surface collision type {collision_type!r} for {item['surface_id']!r}"
            )
        return SurfaceSpec(
            surface_id=str(item["surface_id"]),
            position=tuple(float(v) for v in item["position"]),
            normal=tuple(float(v) for v in item["normal"]),
            bounds_xy=bounds_xy,
            metadata=dict(item),
            surface_type=str(item.get("surface_type", item.get("type", "horizontal"))),
            object_extent_range=extent_range,
            polygon_xy=polygon_xy,
            collision_mesh_path=collision_mesh_path,
            collision_simulation_path=collision_simulation_path,
        )

    @staticmethod
    def _environment_file(environment_dir: Path, value: Any) -> Path:
        path = (environment_dir / str(value)).resolve()
        try:
            path.relative_to(environment_dir.resolve())
        except ValueError as exc:
            raise ValueError(
                f"Surface collision path escapes {environment_dir}: {value}"
            ) from exc
        return path
