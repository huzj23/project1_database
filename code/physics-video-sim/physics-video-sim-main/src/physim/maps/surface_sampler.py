"""Deterministic sampling on predeclared legal surfaces."""

from __future__ import annotations

import numpy as np

from physim.maps import SurfaceSpec


class SurfaceSampler:
    def select_surface(
        self,
        surfaces: tuple[SurfaceSpec, ...],
        object_extent: float,
        allowed_types: tuple[str, ...],
        rng: np.random.Generator,
    ) -> SurfaceSpec:
        candidates = tuple(
            surface
            for surface in surfaces
            if surface.surface_type in allowed_types
            and surface.supports_object_extent(object_extent)
        )
        if not candidates:
            raise ValueError(
                f"No surface accepts object extent {object_extent:.6f} m "
                f"and types {allowed_types}"
            )
        return candidates[int(rng.integers(0, len(candidates)))]

    def sample_position(
        self,
        surface: SurfaceSpec,
        radius: float,
        support_height: float,
        direction_xy: np.ndarray,
        travel_distance: float,
        edge_margin: float,
        rng: np.random.Generator,
    ) -> tuple[float, float, float]:
        xmin, xmax, ymin, ymax = surface.bounds_xy
        margin = radius + edge_margin
        dx, dy = direction_xy * travel_distance
        low_x = xmin + margin - min(0.0, dx)
        high_x = xmax - margin - max(0.0, dx)
        low_y = ymin + margin - min(0.0, dy)
        high_y = ymax - margin - max(0.0, dy)
        if low_x > high_x or low_y > high_y:
            raise ValueError("Surface cannot contain the requested rolling trajectory")
        for _ in range(1000):
            x = float(rng.uniform(low_x, high_x))
            y = float(rng.uniform(low_y, high_y))
            # Sampling multiple points also handles future concave polygons;
            # start/end-only checks are sufficient only for convex regions.
            if all(
                surface.contains_xy(
                    x + float(dx) * step,
                    y + float(dy) * step,
                    margin,
                )
                for step in np.linspace(0.0, 1.0, 17)
            ):
                return (x, y, float(surface.position[2] + support_height))
        raise ValueError("Surface polygon cannot contain the requested rolling trajectory")
