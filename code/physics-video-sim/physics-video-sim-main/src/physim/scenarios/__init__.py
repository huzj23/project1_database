"""Scenario-neutral sample data and scenario factory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from physim.assets import AssetSpec
from physim.maps import MapSpec


@dataclass(frozen=True)
class ControlVariant:
    """One member of a controlled-variable comparison group."""

    variant_id: str
    variable: str | None = None
    multiplier: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioSample:
    """Initial and external conditions passed to the physics adapter."""

    seed: int
    asset_id: str
    map_id: str
    surface_id: str
    position: tuple[float, float, float]
    linear_velocity: tuple[float, float, float]
    angular_velocity: tuple[float, float, float]
    mass: float
    friction: float
    rolling_friction: float
    spinning_friction: float
    restitution: float
    radius: float
    support_height: float
    gravity: tuple[float, float, float]
    video_fps: int
    physics_fps: int
    frame_count: int
    initial_quaternion: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    scenario: str = "rolling"
    variant: ControlVariant = ControlVariant("baseline")
    constant_force: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Bullet's velocity attenuation coefficients.  Default 0.0 keeps every
    # pre-existing scenario unchanged; only the `damping` scenario sets them.
    linear_damping: float = 0.0
    angular_damping: float = 0.0

    # --- driven support body (motions #5 turntable_carry / #6 turntable_spin) --
    # The turntable disc is a SECOND dynamic body that the solver holds by its
    # axis while a constant spin is re-imposed on it every physics substep.  The
    # actor then rides it through contact friction alone.
    #
    # Every field below defaults to "no support body", so the physics adapter's
    # single-body path is selected for all pre-existing scenarios and their
    # samples are bit-identical to before this was added.
    support_asset_id: str | None = None
    #: URDF the physics adapter loads for the disc.  Absolute, resolved by the
    #: scenario from the AssetManager -- never built inside the adapter.
    support_simulation_path: str | None = None
    #: Visual mesh + import kwargs for the disc, resolved by the scenario for the
    #: same reason.  The renderer must not resolve assets itself.
    support_visual_path: str | None = None
    support_render_import_kwargs: dict[str, Any] | None = None
    #: PBR material the disc's own manifest declares (``visual.material``),
    #: resolved by the scenario from the support AssetSpec.  Carried on the
    #: sample for the same reason as the visual path: the renderer applies
    #: materials but does not look assets up.  None means "no material", so
    #: every pre-existing scenario and sample is unchanged.
    support_material: Any | None = None
    support_position: tuple[float, float, float] | None = None
    support_quaternion: tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.0)
    support_mass: float = 0.0
    support_friction: float = 0.0
    support_rolling_friction: float = 0.0
    support_spinning_friction: float = 0.0
    support_restitution: float = 0.0
    #: Disc radius / half-thickness, copied from the resolved support AssetSpec.
    #: NOTE: deliberately NOT called support_height -- ``support_height`` above
    #: is the ACTOR's own support height and is what the validators use.
    support_radius: float = 0.0
    support_half_thickness: float = 0.0
    #: Constant angular velocity re-imposed on the disc every substep (rad/s).
    support_angular_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    #: Distance from the disc axis at which the actor is placed.
    orbit_radius: float = 0.0
    #: z of the surface the actor actually rests on.  For a turntable that is the
    #: disc TOP, not the map surface, so the validator must not reuse the table's
    #: height.  None means "derive from the map surface" (pre-existing behaviour).
    actor_support_z: float | None = None

    #: How the initial pose was resolved, for the dataset record.  A scenario
    #: that never asks for a rotated pose leaves this at ``{"applied": False}``
    #: so its samples -- and therefore its outputs -- are unchanged.
    orientation: dict[str, Any] = field(default_factory=lambda: {"applied": False})
    #: Optional alternative collision URDF for the solver.  Only a sample that
    #: needs a different collision geometry than its manifest declares (the
    #: refined side hull of a rolling object) sets this; None keeps the
    #: manifest's own geometry, so every other scenario is unaffected.
    collision_simulation_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Compatibility for code that imported the phase-one name.
RollingSample = ScenarioSample


class Scenario(Protocol):
    config: dict[str, Any]

    def sample(
        self,
        seed: int,
        asset: AssetSpec,
        map_spec: MapSpec,
        variant: ControlVariant | None = None,
    ) -> ScenarioSample: ...


def variants_from_config(config: dict[str, Any]) -> tuple[ControlVariant, ...]:
    entry = dict(config.get("controlled_variants", {}))
    variable = entry.get("variable")
    multipliers = tuple(float(value) for value in entry.get("multipliers", (1.0,)))
    if not multipliers or any(value <= 0 for value in multipliers):
        raise ValueError("controlled_variants.multipliers must contain positive values")
    labels = tuple(str(value) for value in entry.get("labels", ()))
    if labels and len(labels) != len(multipliers):
        raise ValueError("controlled_variants.labels must match multipliers")
    if not labels:
        labels = tuple(f"x{value:g}" for value in multipliers)
    return tuple(
        ControlVariant(label, str(variable) if variable else None, multiplier)
        for label, multiplier in zip(labels, multipliers)
    )


def reference_variant(config: dict[str, Any]) -> ControlVariant:
    """Return the variant expected to span the largest trajectory."""
    return max(variants_from_config(config), key=lambda item: item.multiplier)


def create_scenario(
    config: dict[str, Any], asset_manager: Any | None = None
) -> Scenario:
    """Build the scenario named by ``config``.

    ``asset_manager`` is optional and only consulted by scenarios that need a
    second resolved asset (the turntable disc); every pre-existing scenario
    ignores it, so existing call sites keep working unchanged.
    """
    scenario_name = str(config["scenario"])
    if scenario_name in ("turntable_carry", "turntable_spin"):
        from physim.scenarios.turntable import TurntableScenario

        return TurntableScenario(config, asset_manager=asset_manager)
    if scenario_name == "rolling":
        from physim.scenarios.rolling import RollingScenario

        return RollingScenario(config)
    if scenario_name == "constant_force":
        from physim.scenarios.constant_force import ConstantForceScenario

        return ConstantForceScenario(config)
    if scenario_name == "free_fall":
        from physim.scenarios.free_fall import FreeFallScenario

        return FreeFallScenario(config)
    if scenario_name == "damping":
        from physim.scenarios.damping import DampingScenario

        return DampingScenario(config)
    raise KeyError(f"Unknown scenario {scenario_name!r}")
