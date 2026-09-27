"""Scenario-neutral sample -> simulate -> validate -> camera -> render -> save."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from physim.assets import AssetManager, AssetSpec
from physim.camera import (
    CameraSpec,
    fixed_camera,
    merge_camera_config,
    perpendicular_camera,
)
from physim.config import load_run_config
from physim.io import DatasetWriter
from physim.maps import MapManager, MapSpec
from physim.physics import SimulationResult
from physim.physics.pybullet_backend import PyBulletBackend
from physim.reference import load_phyco_kubric
from physim.render.blender_backend import PhyCoBlenderBackend
from physim.scenarios import (
    ControlVariant,
    ScenarioSample,
    create_scenario,
    reference_variant,
    variants_from_config,
)
from physim.scenarios.common import object_extent
from physim.validation import ValidationReport, validate_sample


@dataclass(frozen=True)
class PreparedSample:
    project_root: Path
    config: dict[str, Any]
    phyco_sim_root: Path
    asset: AssetSpec
    map_spec: MapSpec
    sample: ScenarioSample
    simulation: SimulationResult
    validation: ValidationReport
    camera: CameraSpec
    camera_reference_variant: ControlVariant


# Compatibility name for local tooling created during phase one.
PreparedRolling = PreparedSample


def _project_path(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def _sample_context(
    config: dict[str, Any],
    seed: int,
    asset_manager: AssetManager,
    map_manager: MapManager,
    variant: ControlVariant,
    asset_id: str | None,
    map_id: str | None,
) -> tuple[AssetSpec, MapSpec, ScenarioSample]:
    scenario_name = str(config["scenario"])
    scenario = create_scenario(config, asset_manager=asset_manager)
    asset_ids = [asset_id] if asset_id else list(config["selection"]["asset_ids"])
    map_ids = [map_id] if map_id else list(config["selection"]["map_ids"])
    rng = np.random.default_rng(np.random.SeedSequence((seed, 0x50485953)))
    pairs = [(map_value, asset_value) for map_value in map_ids for asset_value in asset_ids]
    rng.shuffle(pairs)
    errors: list[str] = []
    for candidate_map, candidate_asset in pairs:
        try:
            asset = asset_manager.get(
                candidate_asset, kind="object", scenario=scenario_name
            )
            map_spec = map_manager.get(candidate_map, scenario=scenario_name)
            sample = scenario.sample(seed, asset, map_spec, variant)
            return asset, map_spec, sample
        except (KeyError, ValueError) as exc:
            errors.append(f"{candidate_map}/{candidate_asset}: {exc}")
    raise ValueError(
        "No configured map/asset pair can produce a legal sample: " + "; ".join(errors)
    )


def _camera_config(
    config: dict[str, Any], map_spec: MapSpec, sample: ScenarioSample
) -> dict[str, Any]:
    surface = map_spec.surface(sample.surface_id)
    camera = merge_camera_config(config["camera"], surface.metadata.get("camera"))
    resolution = config["output"]["resolution"]
    rng = np.random.default_rng(np.random.SeedSequence((sample.seed, 0x43414D45)))
    policy = str(camera.get("policy", "trajectory_side"))
    if policy not in {"trajectory_side", "random", "fixed"}:
        raise ValueError(f"Unsupported camera policy {policy!r}")
    if policy == "fixed":
        # An authored pose is used verbatim, so none of the derived fields below
        # apply and no randomness may be injected into it.  In particular no
        # azimuth offset and no `side` flip, both of which would move a pose the
        # user already approved.
        camera["framing"] = {
            **dict(camera.get("framing", {})),
            "aspect_ratio": float(resolution[0]) / float(resolution[1]),
        }
        return camera
    azimuth_range = camera.get("azimuth_offset_degrees_range")
    if azimuth_range is None:
        azimuth_range = (-180.0, 180.0) if policy == "random" else (0.0, 0.0)
    camera["azimuth_offset_degrees"] = float(
        rng.uniform(float(azimuth_range[0]), float(azimuth_range[1]))
    )
    if str(camera.get("side", "right")) == "random":
        camera["side"] = "left" if int(rng.integers(0, 2)) == 0 else "right"
    camera["framing"] = {
        **dict(camera.get("framing", {})),
        "aspect_ratio": float(resolution[0]) / float(resolution[1]),
    }
    return camera


def prepare_sample(
    config_path: str | Path,
    seed: int | None = None,
    *,
    scenario: str | None = None,
    variant: ControlVariant | None = None,
    asset_id: str | None = None,
    map_id: str | None = None,
    simulation: SimulationResult | None = None,
    camera_override: CameraSpec | None = None,
) -> PreparedSample:
    """Prepare one validated variant and a group-stable trajectory camera."""
    config_path = Path(config_path).resolve()
    project_root = config_path.parent.parent
    config = load_run_config(config_path, scenario=scenario)
    seed = int(config["project"]["seed"] if seed is None else seed)
    config["project"]["seed"] = seed
    variant = variant or variants_from_config(config)[0]
    paths = config["paths"]
    asset_root = _project_path(project_root, paths["asset_root"])
    phyco_sim_root = _project_path(project_root, paths["phyco_sim_root"])
    asset_manager = AssetManager(
        _project_path(project_root, paths["asset_registry"]), asset_root
    )
    map_manager = MapManager(
        _project_path(project_root, paths["map_registry"]), asset_manager
    )
    asset, map_spec, sample = _sample_context(
        config,
        seed,
        asset_manager,
        map_manager,
        variant,
        asset_id,
        map_id,
    )
    physics = PyBulletBackend(phyco_sim_root)
    if simulation is None:
        simulation = physics.simulate(sample, map_spec, asset)
    surface = map_spec.surface(sample.surface_id)
    validation_config = {
        **config["validation"],
        **dict(surface.metadata.get("validation", {})),
    }
    report = validate_sample(simulation, sample, surface, validation_config)
    if not report.valid:
        metrics = json.dumps(report.metrics, sort_keys=True)
        raise RuntimeError(
            f"Physics validation failed: {', '.join(report.reasons)}; metrics={metrics}"
        )

    camera_variant = reference_variant(config)
    if camera_override is not None:
        camera = camera_override
    else:
        if camera_variant == variant:
            camera_simulation = simulation
        else:
            camera_sample = create_scenario(
                config, asset_manager=asset_manager
            ).sample(seed, asset, map_spec, camera_variant)
            camera_simulation = physics.simulate(camera_sample, map_spec, asset)
            camera_report = validate_sample(
                camera_simulation, camera_sample, surface, validation_config
            )
            if not camera_report.valid:
                metrics = json.dumps(camera_report.metrics, sort_keys=True)
                raise RuntimeError(
                    "Camera reference variant failed validation: "
                    + ", ".join(camera_report.reasons)
                    + f"; metrics={metrics}"
                )
        _camera_cfg = _camera_config(config, map_spec, sample)
        if str(_camera_cfg.get("policy", "trajectory_side")) == "fixed":
            camera = fixed_camera(camera_simulation, _camera_cfg)
        else:
            camera = perpendicular_camera(
                camera_simulation,
                _camera_cfg,
                max_object_extent=object_extent(asset),
            )
    return PreparedSample(
        project_root=project_root,
        config=config,
        phyco_sim_root=phyco_sim_root,
        asset=asset,
        map_spec=map_spec,
        sample=sample,
        simulation=simulation,
        validation=report,
        camera=camera,
        camera_reference_variant=camera_variant,
    )


def run_sample(
    config_path: str | Path,
    seed: int | None = None,
    *,
    scenario: str | None = None,
    variant: ControlVariant | None = None,
    asset_id: str | None = None,
    map_id: str | None = None,
) -> Path:
    prepared = prepare_sample(
        config_path,
        seed,
        scenario=scenario,
        variant=variant,
        asset_id=asset_id,
        map_id=map_id,
    )
    project_root = prepared.project_root
    config = prepared.config
    sample = prepared.sample
    paths = config["paths"]
    gpu_ids = config["execution"].get("gpu_ids", [])
    if config["render"].get("device", "CPU").upper() == "GPU":
        os.environ["KUBRIC_USE_GPU"] = "1"
        if gpu_ids and "CUDA_VISIBLE_DEVICES" not in os.environ:
            os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_ids[0])

    sample_id = (
        f"{sample.scenario}__{sample.map_id}__{sample.asset_id}__"
        f"seed-{sample.seed:06d}__{sample.variant.variant_id}"
    )
    group_id = f"seed-{sample.seed:06d}"
    scratch_dir = (
        _project_path(project_root, paths["cache_root"])
        / sample.scenario
        / group_id
        / sample.variant.variant_id
    )
    renderer = PhyCoBlenderBackend(prepared.phyco_sim_root, scratch_dir)
    render_result = renderer.render(
        sample,
        prepared.simulation,
        prepared.asset,
        prepared.map_spec,
        prepared.camera,
        config,
    )
    output_dir = (
        _project_path(project_root, paths["output_root"])
        / sample.scenario
        / group_id
        / sample.variant.variant_id
    )
    kb = load_phyco_kubric(prepared.phyco_sim_root)
    metadata = {
        "schema_version": 2,
        "sample_id": sample_id,
        "scenario": sample.scenario,
        "seed": sample.seed,
        "variant": sample.variant.to_dict(),
        "asset": {
            "id": prepared.asset.asset_id,
            "source_page": prepared.asset.metadata.get("source_page"),
            "license": prepared.asset.metadata.get("license"),
            "sha256": prepared.asset.metadata.get("sha256"),
        },
        "map": {
            "id": prepared.map_spec.map_id,
            "surface_id": sample.surface_id,
            "source_page": prepared.map_spec.metadata.get("source_page"),
            "license": prepared.map_spec.metadata.get("license"),
            "sha256": prepared.map_spec.metadata.get("sha256"),
        },
        "physics": sample.to_dict(),
        "camera": prepared.camera.to_dict(),
        "camera_reference_variant": prepared.camera_reference_variant.to_dict(),
        "validation": prepared.validation.to_dict(),
        "render": render_result.diagnostics,
        "frame_count": len(prepared.simulation.trajectory),
        "modalities": list(config["output"]["modalities"]),
    }
    DatasetWriter(output_dir).write(
        kb, render_result, prepared.simulation, config, metadata
    )
    return output_dir


def run_group(
    config_path: str | Path,
    seed: int,
    *,
    scenario: str | None = None,
) -> tuple[Path, ...]:
    config = load_run_config(config_path, scenario=scenario)
    return tuple(
        run_sample(
            config_path,
            seed,
            scenario=scenario,
            variant=variant,
        )
        for variant in variants_from_config(config)
    )


def prepare_rolling(
    config_path: str | Path,
    seed: int | None = None,
    simulation: SimulationResult | None = None,
) -> PreparedSample:
    return prepare_sample(
        config_path, seed, scenario="rolling", simulation=simulation
    )


def run_rolling(config_path: str | Path, seed: int | None = None) -> Path:
    return run_sample(config_path, seed, scenario="rolling")
