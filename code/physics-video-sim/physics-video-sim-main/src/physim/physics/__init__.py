"""Physics data shared by adapters and validators."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class BodyState:
    frame: int
    time_seconds: float
    position: tuple[float, float, float]
    quaternion: tuple[float, float, float, float]
    linear_velocity: tuple[float, float, float]
    angular_velocity: tuple[float, float, float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimulationResult:
    trajectory: tuple[BodyState, ...]
    collisions: tuple[dict, ...]
    #: Optional trajectory of the driven SUPPORT body (the turntable disc) for
    #: scenarios that simulate a second dynamic body.  Defaults to empty, so
    #: every pre-existing caller constructs and consumes this exactly as before.
    support_trajectory: tuple[BodyState, ...] = ()

    @property
    def has_support_trajectory(self) -> bool:
        return len(self.support_trajectory) > 0


def load_simulation_result(
    trajectory_path: str | Path, collisions_path: str | Path | None = None
) -> SimulationResult:
    """Load a server-produced simulation for an identical local preview."""
    trajectory_data = json.loads(Path(trajectory_path).read_text(encoding="utf-8"))
    trajectory = tuple(
        BodyState(
            frame=int(item["frame"]),
            time_seconds=float(item["time_seconds"]),
            position=tuple(float(value) for value in item["position"]),
            quaternion=tuple(float(value) for value in item["quaternion"]),
            linear_velocity=tuple(float(value) for value in item["linear_velocity"]),
            angular_velocity=tuple(float(value) for value in item["angular_velocity"]),
        )
        for item in trajectory_data
    )
    collisions: tuple[dict, ...] = ()
    if collisions_path is not None and Path(collisions_path).is_file():
        collisions = tuple(
            json.loads(Path(collisions_path).read_text(encoding="utf-8"))
        )
    return SimulationResult(trajectory=trajectory, collisions=collisions)
