"""Thin adapter over PhyCo-Sim's vendored Kubric Blender backend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from physim.assets import AssetSpec
from physim.camera import CameraSpec
from physim.maps import MapSpec
from physim.physics import SimulationResult
from physim.render import RenderResult
from physim.scenarios import ScenarioSample


@dataclass(frozen=True)
class BuiltBlenderScene:
    scene: Any
    renderer: Any
    environment: Any
    simulated_object: Any
    camera: Any
    diagnostics: dict[str, Any]
    support_object: Any = None


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


class PhyCoBlenderBackend:
    def __init__(self, phyco_sim_root: str | Path, scratch_dir: str | Path):
        self.phyco_sim_root = Path(phyco_sim_root)
        self.scratch_dir = Path(scratch_dir)

    def render(
        self,
        sample: ScenarioSample,
        simulation: SimulationResult,
        asset: AssetSpec,
        map_spec: MapSpec,
        camera_spec: CameraSpec,
        config: dict,
    ) -> RenderResult:
        built = self.build_scene(
            sample, simulation, asset, map_spec, camera_spec, config
        )
        import sys as _sys
        _frames = [state.frame for state in simulation.trajectory]
        try:
            import bpy as _bpy
            _cam = _bpy.context.scene.camera
            _mw = _cam.matrix_world.translation if _cam else None
            print(f"DIAG render traj_states={len(simulation.trajectory)} "
                  f"render_frames={len(_frames)} first={_frames[0]} last={_frames[-1]}",
                  file=_sys.stderr, flush=True)
            print(f"DIAG blender camera={None if _mw is None else (round(_mw.x,3), round(_mw.y,3), round(_mw.z,3))} "
                  f"frame_start={_bpy.context.scene.frame_start} "
                  f"frame_end={_bpy.context.scene.frame_end} "
                  f"res={tuple(_bpy.context.scene.render.resolution_x for _ in [0])}"
                  f"x{_bpy.context.scene.render.resolution_y}",
                  file=_sys.stderr, flush=True)
        except Exception as _e:
            print(f"DIAG camera probe failed: {_e}", file=_sys.stderr, flush=True)
        layers = built.renderer.render(
            frames=_frames,
            return_layers=("rgba", "depth", "segmentation"),
        )
        try:
            print(f"DIAG rendered rgba={layers['rgba'].shape} depth={layers['depth'].shape}",
                  file=_sys.stderr, flush=True)
        except Exception:
            pass
        return RenderResult(
            rgb=layers["rgba"][..., :3],
            depth=layers["depth"],
            segmentation=layers["segmentation"],
            diagnostics=built.diagnostics,
        )

    def build_scene(
        self,
        sample: ScenarioSample,
        simulation: SimulationResult,
        asset: AssetSpec,
        map_spec: MapSpec,
        camera_spec: CameraSpec,
        config: dict,
    ) -> BuiltBlenderScene:
        _purged = purge_stale_frames(self.scratch_dir)
        if _purged:
            import sys as _sys
            print(f"DIAG purged {_purged} stale frame files from {self.scratch_dir}",
                  file=_sys.stderr, flush=True)
        """Build the shared animated Blender scene without starting a render."""
        # Blender 3.4's bundled glTF importer still uses the removed NumPy alias.
        import numpy as np

        if "bool" not in np.__dict__:
            np.bool = np.bool_  # type: ignore[attr-defined]

        from physim.reference import load_phyco_kubric

        kb = load_phyco_kubric(self.phyco_sim_root)
        from kubric.renderer import Blender

        environment_render = dict(map_spec.metadata.get("render", {}))
        ambient = tuple(
            float(value)
            for value in environment_render.get(
                "ambient_illumination", (0.35, 0.35, 0.35)
            )
        )
        background = tuple(
            float(value)
            for value in environment_render.get("background", (0.06, 0.08, 0.12))
        )
        scene = kb.Scene(
            frame_start=1,
            frame_end=sample.frame_count,
            frame_rate=sample.video_fps,
            step_rate=sample.physics_fps,
            resolution=tuple(int(v) for v in config["output"]["resolution"]),
            gravity=sample.gravity,
            ambient_illumination=kb.Color(*ambient),
            background=kb.Color(*background),
        )
        renderer = Blender(
            scene,
            scratch_dir=self.scratch_dir,
            adaptive_sampling=bool(
                config["render"].get("use_adaptive_sampling", True)
            ),
            use_denoising=bool(config["render"]["use_denoising"]),
            samples_per_pixel=int(config["render"]["samples_per_pixel"]),
            default_layers=("Image", "Depth"),
            aux_layers=("CryptoObject00",),
            verbose=False,
        )
        import bpy

        render_engine = str(config["render"].get("engine", "CYCLES")).upper()
        if render_engine not in {"CYCLES", "BLENDER_EEVEE"}:
            raise ValueError(f"Unsupported Blender render engine {render_engine!r}")
        bpy.context.scene.render.engine = render_engine
        if render_engine == "BLENDER_EEVEE":
            bpy.context.scene.eevee.taa_render_samples = int(
                config["render"]["samples_per_pixel"]
            )
        else:
            cycles = bpy.context.scene.cycles
            cycles.use_adaptive_sampling = bool(
                config["render"].get("use_adaptive_sampling", True)
            )
            cycles.adaptive_threshold = float(
                config["render"].get("adaptive_threshold", 0.01)
            )
            for setting in (
                "max_bounces",
                "diffuse_bounces",
                "glossy_bounces",
                "transmission_bounces",
                "transparent_max_bounces",
                "volume_bounces",
            ):
                config_name = (
                    "transparent_bounces"
                    if setting == "transparent_max_bounces"
                    else setting
                )
                if config_name in config["render"]:
                    setattr(cycles, setting, int(config["render"][config_name]))
        view_settings = bpy.context.scene.view_settings
        view_settings.view_transform = str(
            config["render"].get("view_transform", "Filmic")
        )
        view_settings.look = str(config["render"].get("look", "Medium High Contrast"))
        view_settings.exposure = float(config["render"].get("exposure", 0.0))
        view_settings.gamma = float(config["render"].get("gamma", 1.0))
        environment = kb.FileBasedObject(
            name="environment",
            asset_id=map_spec.map_id,
            render_filename=str(map_spec.visual_path),
            simulation_filename=None,
            scale=map_spec.visual_scale,
            render_import_kwargs=map_spec.render_import_kwargs,
            static=True,
            background=True,
            segmentation_id=1,
        )
        simulated_object = kb.FileBasedObject(
            name="simulated_object",
            asset_id=asset.asset_id,
            render_filename=str(asset.visual_path),
            simulation_filename=None,
            scale=asset.scale,
            render_import_kwargs=asset.render_import_kwargs,
            position=simulation.trajectory[0].position,
            static=False,
            segmentation_id=2,
        )
        # The turntable disc is a second RENDERED body.  It is added only when
        # the simulation actually carries a support trajectory, so the
        # single-body scenes are built exactly as before.  The disc's mesh and
        # import kwargs arrive on the sample: the scenario resolves assets, the
        # renderer does not.
        support_object = None
        if simulation.support_trajectory and sample.support_visual_path:
            support_object = kb.FileBasedObject(
                name="support_object",
                asset_id=str(sample.support_asset_id),
                render_filename=str(sample.support_visual_path),
                simulation_filename=None,
                scale=(1.0, 1.0, 1.0),
                # The disc's visual OBJ was exported Z-up from Blender while
                # bpy.ops.import_scene.obj defaults to Y-up, which would lay the
                # disc on its side.  Asking for the convention it was written in
                # is what makes it import as a flat disc rather than a wheel.
                render_import_kwargs={
                    **dict(sample.support_render_import_kwargs or {}),
                    "axis_forward": "Y",
                    "axis_up": "Z",
                },
                position=simulation.support_trajectory[0].position,
                static=False,
                segmentation_id=3,
            )
            # The disc's asset declares a PBR material (see materials.py); the
            # spec travels on the sample so the renderer stays free of manifest
            # and AssetManager lookups.
            support_object.render_material = getattr(sample, "support_material", None)
        camera = kb.PerspectiveCamera(
            name="side_camera",
            position=camera_spec.position,
            focal_length=camera_spec.focal_length_mm,
        )
        camera.look_at(camera_spec.look_at)
        scene += [environment, simulated_object]
        if support_object is not None:
            scene += [support_object]
        scene += [camera]
        scene.camera = camera
        import sys as _sys
        print(f"DIAG build_scene camera_spec={tuple(round(v,3) for v in camera_spec.position)} "
              f"look={tuple(round(v,3) for v in camera_spec.look_at)} "
              f"focal={camera_spec.focal_length_mm}", file=_sys.stderr, flush=True)
        environment_object = environment.linked_objects[renderer]
        visual_object = simulated_object.linked_objects[renderer]
        camera_object = camera.linked_objects[renderer]
        environment_object.name = f"environment__{map_spec.environment_asset_id}"
        visual_object.name = f"asset__{asset.asset_id}"
        camera_object.name = "camera__side_perpendicular"
        self._apply_visual_transform(
            environment_object, map_spec.metadata.get("visual_transform", {})
        )
        self._apply_visual_transform(
            visual_object, asset.metadata.get("visual_transform", {})
        )
        # ------------------------------------------------------------------
        # Declarative PBR materials.
        #
        # A manifest may declare ``visual.material`` (see physim/render/materials.py).
        # Applying it here -- after the objects exist in Blender and before the
        # render -- is what makes the turntable disc come out as the frozen
        # ``dark_wood`` instead of Blender's default grey.
        #
        # ``render_material`` is read with getattr: Kubric's object traits are
        # dynamically defined, so an attribute set at construction time (the
        # support disc) is not a declared trait.  ``asset.material`` is read the
        # same way so a caller may attach a material to a lightweight object that
        # only mimics AssetSpec.
        # ------------------------------------------------------------------
        from physim.render.materials import apply_declared_material

        declared_materials: dict[str, Any] = {}
        material_requests = (
            ("simulated_object", visual_object, getattr(asset, "material", None)),
            (
                "support_object",
                support_object.linked_objects[renderer] if support_object is not None else None,
                getattr(support_object, "render_material", None),
            ),
        )
        for role, target, spec in material_requests:
            if spec is None:
                continue
            declared_materials[role] = apply_declared_material(
                target, spec, self.phyco_sim_root
            )
        # Purely informational; an asset that declares a material but did not get
        # a rendered object still shows up here as "not applied".
        for role, _target, spec in material_requests:
            if spec is not None and role not in declared_materials:
                declared_materials[role] = {"pbr": spec.pbr, "applied_to": None}
        authored_lights, authored_world = self._append_authored_lighting(
            map_spec.visual_path
        )
        supplemental_lights = self._add_configured_blender_lights(
            environment_render.get("supplemental_lights", ()),
            "environment_supplemental_lighting",
        )
        fallback_lights = []
        if authored_lights:
            lighting_source = (
                "source_blend+supplemental"
                if supplemental_lights
                else "source_blend"
            )
        elif supplemental_lights:
            lighting_source = "supplemental"
        else:
            lighting_source = "asset_fallback"
            light_specs = environment_render.get(
                "area_lights",
                [
                    {
                        "name": "key_light",
                        "position": (0.0, -2.0, 10.0),
                        "look_at": (0.0, 0.0, 0.0),
                        "intensity": 1100.0,
                        "width": 8.0,
                        "height": 8.0,
                    }
                ],
            )
            for index, light_spec in enumerate(light_specs):
                light = kb.RectAreaLight(
                    name=str(light_spec.get("name", f"area_light_{index}")),
                    position=tuple(float(value) for value in light_spec["position"]),
                    intensity=float(light_spec["intensity"]),
                    width=float(light_spec["width"]),
                    height=float(light_spec["height"]),
                )
                light.look_at(
                    tuple(
                        float(value)
                        for value in light_spec.get("look_at", (0, 0, 0))
                    )
                )
                fallback_lights.append(light)
            scene += fallback_lights
        fallback_light_objects = [
            light.linked_objects[renderer] for light in fallback_lights
        ]
        environment_light_objects = (
            authored_lights + supplemental_lights + fallback_light_objects
        )
        bpy.context.view_layer.update()
        environment_materials = [
            material
            for material in environment_object.data.materials
            if material is not None
        ]
        render_diagnostics = {
            "render_engine": render_engine,
            "cycles_device": str(bpy.context.scene.cycles.device),
            "resolution": [int(value) for value in scene.resolution],
            "video_fps": sample.video_fps,
            "frame_count": sample.frame_count,
            "samples_per_pixel": int(config["render"]["samples_per_pixel"]),
            "use_denoising": bool(config["render"]["use_denoising"]),
            "use_adaptive_sampling": bool(
                config["render"].get("use_adaptive_sampling", True)
            ),
            "adaptive_threshold": float(
                config["render"].get("adaptive_threshold", 0.01)
            ),
            "view_transform": str(view_settings.view_transform),
            "look": str(view_settings.look),
            "asset_dimensions": [float(v) for v in visual_object.dimensions],
            "environment_dimensions": [float(v) for v in environment_object.dimensions],
            "environment_material_count": len(environment_materials),
            "environment_image_texture_nodes": sum(
                1
                for material in environment_materials
                if material.use_nodes
                for node in material.node_tree.nodes
                if node.type == "TEX_IMAGE" and node.image is not None
            ),
            "environment_uv_layer_count": len(environment_object.data.uv_layers),
            "environment_lighting_source": lighting_source,
            "declared_materials": declared_materials,
            "environment_light_count": len(environment_light_objects),
            "environment_light_types": [
                light.data.type for light in environment_light_objects
            ],
            "environment_area_light_count": sum(
                light.data.type == "AREA" for light in environment_light_objects
            ),
            "environment_supplemental_light_count": len(supplemental_lights),
            "environment_authored_world": (
                authored_world.name if authored_world is not None else None
            ),
            "camera_position": [float(v) for v in camera_object.location],
            "camera_focal_length_mm": float(camera_object.data.lens),
            "camera_sensor_width_mm": float(camera_object.data.sensor_width),
            "enabled_compute_devices": [
                device.name
                for device in bpy.context.preferences.addons["cycles"].preferences.devices
                if device.use
            ],
        }
        print(f"RENDER_DIAGNOSTICS={render_diagnostics}")
        # Blender does NOT animate by itself: if the solver's states are not
        # transcribed into keyframes here, every rendered frame is byte-identical
        # to the first.  This is the replay step -- the trajectory itself was
        # produced entirely by PyBullet.
        for state in simulation.trajectory:
            simulated_object.position = state.position
            simulated_object.quaternion = state.quaternion
            simulated_object.keyframe_insert("position", state.frame)
            simulated_object.keyframe_insert("quaternion", state.frame)
        if support_object is not None:
            # The disc is keyframed from the solver's own disc trajectory, so the
            # rendered spin is the one PyBullet integrated rather than a
            # re-derived angle.
            for state in simulation.support_trajectory:
                support_object.position = state.position
                support_object.quaternion = state.quaternion
                support_object.keyframe_insert("position", state.frame)
                support_object.keyframe_insert("quaternion", state.frame)
        return BuiltBlenderScene(
            scene=scene,
            renderer=renderer,
            environment=environment,
            simulated_object=simulated_object,
            camera=camera,
            diagnostics=render_diagnostics,
            support_object=support_object,
        )

    @staticmethod
    def _apply_visual_transform(blender_object, transform: dict) -> None:
        """Undo the fork's GLB axis convention and optionally center visual geometry."""
        import math

        from mathutils import Matrix, Vector

        angle = float(transform.get("x_rotation_degrees", 0.0))
        if angle:
            blender_object.data.transform(Matrix.Rotation(math.radians(angle), 4, "X"))
        if transform.get("center_mesh_origin", False):
            vertices = [vertex.co for vertex in blender_object.data.vertices]
            lower = Vector(tuple(min(vertex[axis] for vertex in vertices) for axis in range(3)))
            upper = Vector(tuple(max(vertex[axis] for vertex in vertices) for axis in range(3)))
            blender_object.data.transform(Matrix.Translation(-(lower + upper) / 2.0))
        blender_object.data.update()

    @staticmethod
    def _append_authored_lighting(blend_path: Path):
        """Append the normalized source light collection and World, if present."""
        if blend_path.suffix.lower() != ".blend":
            return [], None

        import bpy

        collection_name = "environment_lighting"
        world_name = "environment_world"
        with bpy.data.libraries.load(str(blend_path), link=False) as (source, target):
            target.collections = (
                [collection_name] if collection_name in source.collections else []
            )
            target.worlds = [world_name] if world_name in source.worlds else []

        lighting_collection = next(
            (collection for collection in target.collections if collection is not None),
            None,
        )
        lights = []
        if lighting_collection is not None:
            bpy.context.scene.collection.children.link(lighting_collection)
            lights = [
                obj for obj in lighting_collection.all_objects if obj.type == "LIGHT"
            ]

        authored_world = next(
            (world for world in target.worlds if world is not None), None
        )
        if authored_world is not None:
            bpy.context.scene.world = authored_world
        return lights, authored_world

    @staticmethod
    def _add_configured_blender_lights(light_specs, collection_name: str):
        """Add explicit per-environment supplements without changing source lights."""
        if not light_specs:
            return []

        import bpy
        from mathutils import Vector

        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
        lights = []
        for index, raw_spec in enumerate(light_specs):
            spec = dict(raw_spec)
            light_type = str(spec.get("type", "AREA")).upper()
            if light_type not in {"AREA", "SUN"}:
                raise ValueError(f"Unsupported configured light type: {light_type}")
            name = str(spec.get("name", f"supplemental_light_{index}"))
            data = bpy.data.lights.new(name=name, type=light_type)
            data.energy = float(spec["intensity"])
            data.color = tuple(
                float(value) for value in spec.get("color", (1.0, 1.0, 1.0))
            )
            obj = bpy.data.objects.new(name=name, object_data=data)
            collection.objects.link(obj)
            obj.location = tuple(
                float(value) for value in spec.get("position", (0.0, 0.0, 0.0))
            )
            if light_type == "AREA":
                data.shape = "RECTANGLE"
                data.size = float(spec["width"])
                data.size_y = float(spec.get("height", spec["width"]))
            if "look_at" in spec:
                direction = Vector(spec["look_at"]) - obj.location
                obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
            elif "rotation_euler" in spec:
                obj.rotation_euler = tuple(
                    float(value) for value in spec["rotation_euler"]
                )
            lights.append(obj)
        return lights
