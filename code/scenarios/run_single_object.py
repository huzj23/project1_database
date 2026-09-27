"""Entry point: generate a single-object, non-interactive physics simulation asset.

Run through Blender's bundled interpreter (``bpy`` is only available there)::

    blender.exe --background --factory-startup \
        --python code/scenarios/run_single_object.py -- \
        --motion circular --object ball --output_dir outcomes/circular --save_mp4

Every run writes a directory ``<output_dir>/<video_id>/`` containing:

    rgba_00000.jpg            RGB frames
    segmentation_00000.png    instance-id masks (lossless uint16)
    depth_00000.png           16-bit depth in millimetres (0 == invalid)
    metadata.json             full physical annotation (see below)
    rgb.mp4 / segmentation.mp4 / depth.mp4    (with --save_mp4)

``metadata.json`` carries the scene/camera description plus a per-frame
``frames[]`` array holding position, quaternion, velocity, acceleration and
angular velocity for every object -- i.e. the physical labels for the video.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
import uuid

# --------------------------------------------------------------------------------------
# Bootstrap: make the scenario package importable before anything else.
# --------------------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import phyco_common as pc  # noqa: E402
import phyco_motions as pm  # noqa: E402
import phyco_backdrops as pb  # noqa: E402

pc.bootstrap_syspath()
# Blender 3.4's bundled glTF importer still calls np.bool and friends, which NumPy
# removed in 1.24.  Must run before any .glb import (ReplicaCAD interiors).
pc.patch_numpy_legacy_aliases()

import numpy as np  # noqa: E402

import kubric as kb  # noqa: E402


# --------------------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------------------

def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="run_single_object",
        description="Generate a single-object physics simulation asset.",
    )
    parser.add_argument("--motion", choices=["circular", "damped", "rotation"],
                        required=True)
    parser.add_argument("--object", default=None,
                        help=f"mesh to simulate; one of {sorted(pc.ASSETS)}")
    parser.add_argument("--output_dir", default=os.path.join(pc.OUTCOMES_DIR, "single_object"))
    parser.add_argument("--video_id", default=None)
    parser.add_argument("--resolution", default="768x432")
    parser.add_argument("--frame_end", type=int, default=96,
                        help="index of the last frame (inclusive)")
    parser.add_argument("--frame_rate", type=int, default=24)
    parser.add_argument("--step_rate", type=int, default=240)
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--threads", type=int, default=0,
                        help="Cycles render threads per process; 0 = Blender default. "
                             "Set this when running several workers in parallel so the "
                             "machine is not oversubscribed.")
    parser.add_argument("--no_denoise", action="store_true")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--layers", default="image,segmentation,depth")
    parser.add_argument("--save_mp4", action="store_true")
    parser.add_argument("--hdri", default=None,
                        help="HDRI id from the local cache; omit for analytic lighting")
    parser.add_argument("--scale", type=float, default=None,
                        help="object scale (default: motion-specific)")
    parser.add_argument("--color", default="red")
    parser.add_argument("--ground_size", type=float, default=3.5)
    parser.add_argument("--look", choices=["studio", "interior", "plain"],
                        default="studio",
                        help="studio = cyclorama + 3-point softbox (reference recipe); "
                             "interior = ReplicaCAD apartment backdrop; "
                             "plain = legacy single ground plane + analytic lights")
    parser.add_argument("--stage", default="frl_apartment_stage",
                        help="ReplicaCAD stage name for --look interior")
    parser.add_argument("--floor_material", default="concrete_floor_worn_001",
                        help="Poly Haven PBR material for the studio floor")
    parser.add_argument("--hdri_name", default=None,
                        help="override the backdrop HDRI (plain .hdr in models/hdri_hdr)")
    parser.add_argument("--motion_blur", type=float, default=0.25,
                        help="Cycles shutter in frames; 0 disables motion blur")
    parser.add_argument("--frame_format", choices=["png", "jpg"], default="png",
                        help="RGB frame container. PNG is lossless (reference recipe)")
    parser.add_argument("--camera_elevation", type=float, default=14.0)
    parser.add_argument("--camera_azimuth", type=float, default=-62.0)
    parser.add_argument("--camera_margin", type=float, default=0.12,
                        help="fraction of the frame kept clear around the trajectory")
    parser.add_argument("--focal_length", type=float, default=55.0,
                        help="lens focal length in mm (reference recipe uses 55)")
    parser.add_argument("--sensor_width", type=float, default=36.0)
    parser.add_argument("--camera_distance", type=float, default=5.5,
                        help="fixed camera distance for --look studio/interior")
    parser.add_argument("--camera_target_z", type=float, default=0.9,
                        help="height the backdrop camera aims at (plain look only)")
    parser.add_argument("--camera_min_distance", type=float, default=0.0,
                        help="closest the auto-framer may place a backdrop camera (0 = unbounded)")
    parser.add_argument("--camera_max_distance", type=float, default=0.0,
                        help="farthest the auto-framer may place a backdrop camera (0 = unbounded)")
    parser.add_argument("--qa_sheet", action="store_true",
                        help="also write a small QA contact sheet")

    # circular motion
    g = parser.add_argument_group("circular")
    g.add_argument("--radius", type=float, default=1.2)
    g.add_argument("--period", type=float, default=2.0,
                   help="seconds per revolution (physical control)")
    g.add_argument("--turns", type=float, default=None,
                   help="revolutions across the clip; overrides --period")
    g.add_argument("--plane", choices=["x", "y", "z"], default="z")
    g.add_argument("--spin_per_orbit", type=float, default=1.0,
                   help="body self-rotation revolutions per orbit (0 disables spin)")
    g.add_argument("--height", type=float, default=0.9,
                   help="height of the circle centre above the ground")

    # damped motion
    d = parser.add_argument_group("damped")
    d.add_argument("--speed", type=float, default=3.0, help="initial speed in m/s")
    d.add_argument("--direction", type=float, default=0.0,
                   help="initial heading in degrees, measured in the XY plane")
    d.add_argument("--spin_rate", type=float, default=6.0,
                   help="initial angular speed in rad/s")
    d.add_argument("--linear_damping", type=float, default=1.2,
                   help="decay rate k in 1/s (travel distance == speed / k)")
    d.add_argument("--angular_damping", type=float, default=1.5)
    d.add_argument("--no_ground", action="store_true")

    # rotation
    r = parser.add_argument_group("rotation")
    r.add_argument("--spin_axis", choices=["x", "y", "z"], default="z")
    r.add_argument("--spin_period", type=float, default=4.0,
                   help="seconds per revolution for the rotation scenario")
    r.add_argument("--spin_damping", type=float, default=0.0,
                   help="angular decay rate in 1/s; 0 keeps the spin uniform")

    parser.add_argument("--hdri_random", action="store_true",
                        help="pick a random HDRI from the local cache (seeded)")
    parser.add_argument("--no_hdri", action="store_true",
                        help="force analytic lighting even if --hdri_random is set")

    # Two invocation styles are supported:
    #   blender --background --python run_single_object.py -- --motion ...
    #   python run_single_object.py --motion ...          (bpy installed as a wheel)
    # Blender consumes its own argv, so it needs the '--' separator; a plain
    # interpreter passes the script path as argv[0].
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    return parser.parse_args(argv)


def _layer_set(text):
    return {s.strip().lower() for s in text.split(",") if s.strip()}


# --------------------------------------------------------------------------------------
# Camera framing
# --------------------------------------------------------------------------------------

def _framing_distance(span, resolution, focal_length=42.0, sensor_width=36.0,
                      fill=0.80, floor=2.0):
    """Distance at which a horizontal span fills ``fill`` of the frame width.

    Uses the horizontal field of view because every scenario here spans the
    image horizontally; evaluated analytically so it can run before the camera
    object exists.
    """
    fov_h = 2.0 * np.arctan(sensor_width / (2.0 * focal_length))
    return max((span / 2.0) / (fill * np.tan(fov_h / 2.0)), floor)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def main(argv):
    args = parse_args(argv)
    np.random.seed(args.seed)

    video_id = args.video_id or f"{args.motion}_{uuid.uuid4().hex[:8]}"
    out_dir = os.path.join(args.output_dir, video_id)
    os.makedirs(out_dir, exist_ok=True)

    layers = _layer_set(args.layers)
    render_layers = []
    if "image" in layers:
        render_layers.append("rgba")
    if "segmentation" in layers:
        render_layers.append("segmentation")
    if "depth" in layers:
        render_layers.append("depth")
    if not render_layers:
        raise SystemExit("--layers selected no outputs")

    n_frames = args.frame_end + 1
    fps = float(args.frame_rate)
    res_w, res_h = pc.parse_resolution(args.resolution)

    obj_name = args.object or {"circular": "ball", "damped": "brick_box",
                               "rotation": "brick_box"}[args.motion]
    asset = pc.get_asset(obj_name)

    scale = args.scale
    if scale is None:
        scale = {"circular": 0.45, "damped": 0.60, "rotation": 0.60}[args.motion]

    # Contact regime: no scenario here involves contact by construction.
    # Circular motion is a prescribed orbit, damping a prescribed exponential
    # decay, rotation a prescribed spin.  A floor is included for circular and
    # rotation as a static depth reference the body never touches.
    contact_mode = False
    with_ground = (not args.no_ground) and args.motion in ("circular", "rotation")
    gravity = (0.0, 0.0, 0.0)

    print(f"[phyco] motion={args.motion} object={asset.name} frames={n_frames} "
          f"res={res_w}x{res_h} scale={scale} contact={contact_mode}", flush=True)

    scene_spec = pc.SceneSpec(
        resolution=(res_w, res_h),
        frame_start=0, frame_end=args.frame_end,
        frame_rate=args.frame_rate, step_rate=args.step_rate,
        gravity=gravity, samples=args.samples,
        use_denoising=not args.no_denoise,
    )
    scene, renderer, simulator, scratch = pc.make_scene(kb, scene_spec)
    if args.threads and args.threads > 0:
        # Cycles otherwise spawns one thread per core in *every* worker process,
        # which thrashes when several runs share the machine.
        import bpy
        bpy.context.scene.render.threads_mode = "FIXED"
        bpy.context.scene.render.threads = int(args.threads)
    print(f"[phyco] scene ready; scratch={scratch} threads={args.threads or 'auto'}",
          flush=True)

    # ---- backdrop (Track A studio / Track B interior / legacy plain) -----------------
    # The backdrop supplies its own floor and lighting, so the legacy ground plane
    # and analytic lights are skipped whenever a backdrop is used.
    backdrop_info = {"backdrop": "plain"}
    look_at = (0.0, 0.0, args.height)

    if args.look == "studio":
        spec = pb.StudioSpec(
            floor_material=args.floor_material,
            hdri=args.hdri_name or "empty_warehouse_01",
            motion_blur_shutter=args.motion_blur,
        )
        backdrop_info = pb.build_studio(kb, scene, renderer, spec, ground_z=0.0)
        with_ground = False
        print(f"[phyco] backdrop=studio floor={args.floor_material} "
              f"hdri={spec.hdri} shutter={args.motion_blur}", flush=True)
    elif args.look == "interior":
        spec = pb.InteriorSpec(stage=args.stage,
                               hdri=args.hdri_name or "empty_warehouse_01",
                               motion_blur_shutter=args.motion_blur)
        backdrop_info = pb.build_interior(kb, scene, renderer, spec, look_at=look_at)
        with_ground = False
        print(f"[phyco] backdrop=interior stage={args.stage} shutter={args.motion_blur}",
              flush=True)
        b = pb.stage_bounds()
        if b:
            backdrop_info["stage_bounds"] = {"min": list(b[0]), "max": list(b[1])}
            print(f"[phyco] stage bounds min={tuple(round(v,1) for v in b[0])} "
                  f"max={tuple(round(v,1) for v in b[1])}", flush=True)
    else:
        # Legacy path: single ground plane + analytic lights (or cache HDRI).
        if with_ground:
            pc.add_ground(kb, scene, size=args.ground_size)
        if args.hdri_random and not args.no_hdri:
            cached = pc.list_cached_hdris()
            if cached:
                chosen = cached[int(np.random.RandomState(args.seed).randint(len(cached)))]
                pc.enable_hdri(renderer, chosen)
                backdrop_info = {"backdrop": "plain", "hdri": {"id": chosen}}
        else:
            pc.add_lighting(kb, scene)
            pc.set_background(renderer, scene)

    # ---- the single simulated object ------------------------------------------------
    obj = kb.FileBasedObject(
        name=asset.name,
        simulation_filename=asset.urdf_path,
        render_filename=asset.obj_path,
        scale=scale,
        position=(0.0, 0.0, args.height),
        segmentation_id=2,
    )
    try:
        obj.material = kb.PrincipledBSDFMaterial(color=kb.Color.from_name(args.color))
    except Exception:
        obj.material = kb.PrincipledBSDFMaterial(color=(0.8, 0.15, 0.15, 1.0))
    scene += obj
    print(f"[phyco] object loaded (seg_id=2)", flush=True)

    # ---- motion ----------------------------------------------------------------------
    annotation = {}
    motion_meta = {"type": args.motion}

    # The meshes are not centred on their own origin; their URDF <inertial><origin>
    # gives the centre of mass in mesh-local units.  Trajectories are specified at
    # the centre of mass (the physically meaningful point to annotate) and converted
    # to mesh-origin placement at keyframe time.
    _urdf = pc.read_urdf_inertia(asset.urdf_path)
    com_local = _urdf.get("origin") or [0.0, 0.0, 0.0]
    origin_offset_local = [scale * v for v in com_local]
    motion_meta["mesh_local_com"] = list(com_local)
    motion_meta["com_offset_world_m"] = list(origin_offset_local)
    if any(abs(v) > 1e-9 for v in origin_offset_local):
        print(f"[phyco] centre-of-mass offset (world m): "
              f"{[round(v, 4) for v in origin_offset_local]}", flush=True)

    if args.motion == "circular":
        duration = (n_frames - 1) / fps
        period = (duration / args.turns) if args.turns else args.period
        spec = pm.CircularSpec(
            radius=args.radius, period_s=period,
            center=(0.0, 0.0, args.height), axis=args.plane,
            spin_per_orbit=args.spin_per_orbit,
        )
        states = pm.apply_circular(kb, obj, spec, n_frames, fps, origin_offset_local)
        annotation = {str(f): {asset.name: s} for f, s in states.items()}
        motion_meta.update({
            "radius": args.radius, "plane": args.plane,
            "center": list(spec.center),
            "period_s": spec.period_s,
            "revolutions_in_clip": duration / spec.period_s,
            "omega_rad_s": spec.omega,
            "tangential_speed": spec.tangential_speed,
            "centripetal_accel": spec.centripetal_accel,
            "spin_per_orbit": args.spin_per_orbit,
            "gravity": list(gravity),
            "dynamics": "analytic_kinematic",
            "closed_loop": True,
        })
        # the camera target is the circle centre
        look_at = spec.center
        cam_dist = None

    elif args.motion == "damped":
        spec = pm.DampedSpec(
            speed=args.speed,
            direction_deg=args.direction,
            linear_damping=args.linear_damping,
            angular_damping=args.angular_damping,
            spin_rate=args.spin_rate,
            start=(0.0, 0.0, args.height),
        )
        states = pm.apply_damped(kb, obj, spec, n_frames, fps, origin_offset_local)
        annotation = {str(f): {asset.name: s} for f, s in states.items()}
        decay = pm.verify_exponential_decay(states, fps, spec.linear_damping)
        motion_meta.update({
            "initial_speed": args.speed,
            "direction_deg": args.direction,
            "linear_damping": args.linear_damping,
            "angular_damping": args.angular_damping,
            "spin_rate": args.spin_rate,
            "travel_distance": spec.travel_distance,
            "start_position": list(spec.start_position),
            "gravity": list(gravity),
            "dynamics": "analytic_viscous_damping",
            "model": "v(t) = v0*exp(-k*t); x(t) = x0 + (v0/k)*(1-exp(-k*t))",
            "decay_verification": decay,
        })
        print(f"[phyco] damped trajectory: v0={args.speed} k={args.linear_damping} "
              f"travel={spec.travel_distance:.2f}m "
              f"v_end={decay['speed_last']:.4f} (fit k={decay['fitted_damping']:.4f})",
              flush=True)

        look_at = (spec.start_position[0] + 0.5 * spec.travel_distance
                   * np.cos(np.deg2rad(args.direction)),
                   spec.start_position[1] + 0.5 * spec.travel_distance
                   * np.sin(np.deg2rad(args.direction)),
                   args.height)
        cam_dist = None

    else:  # rotation
        urdf_info = pc.read_urdf_inertia(asset.urdf_path)
        I_axis = pc.principal_moment(urdf_info.get("inertia"), args.spin_axis)
        spec = pm.RotationSpec(
            axis=args.spin_axis,
            period_s=args.spin_period,
            angular_damping=args.spin_damping,
            center=(0.0, 0.0, args.height),
            mass=urdf_info.get("mass"),
            moment_of_inertia=I_axis,
        )
        states = pm.apply_rotation(kb, obj, spec, n_frames, fps, origin_offset_local)
        annotation = {str(f): {asset.name: s} for f, s in states.items()}
        check = pm.verify_rotation(states, fps, spec.omega0, args.spin_damping)
        motion_meta.update({
            "axis": args.spin_axis,
            "center": list(spec.center),
            "period_s": spec.period_s,
            "omega_rad_s": spec.omega0,
            "angular_damping": args.spin_damping,
            "gravity": list(gravity),
            "dynamics": ("analytic_uniform_rotation" if args.spin_damping == 0
                         else "analytic_decaying_rotation"),
            "urdf_inertia": urdf_info,
            "moment_of_inertia_about_axis": I_axis,
            "rotation_verification": check,
        })
        print(f"[phyco] rotation: axis={args.spin_axis} omega={spec.omega0:.4f} rad/s "
              f"revolutions={check['revolutions']:.3f} "
              f"I={I_axis if I_axis is None else round(I_axis, 6)}", flush=True)

        look_at = spec.center
        cam_dist = None

    # ---- trajectory generation ----------------------------------------------------------
    # Every scenario is a prescribed (analytic) trajectory keyframed onto the asset:
    #   * circular -- a fixed orbit; no solver can produce a perfectly closed circle
    #   * damped   -- the exact solution of the viscous-damping ODE
    #   * rotation -- uniform (or exponentially decaying) spin about a fixed axis
    # See phyco_motions for why solver-side damping is unusable in this PyBullet build.
    sim_meta = {"dynamics": motion_meta.get("dynamics"),
                "solver": "none (prescribed trajectory)"}

    # ---- camera: auto-framed from the real trajectory -----------------------------------
    # Include the body's own extent, otherwise a straight-line or stationary
    # trajectory has no spread and the auto-framer collapses onto a degenerate view.
    # The meshes are NOT centred on their own origin (the ball's vertices sit around
    # local z = 1.0), so corners are taken relative to the *centre of mass* -- the
    # same reference the trajectory uses.  Raw local corners would bias the framing
    # box by the COM offset and push the body out of frame.
    lo, hi = pc.mesh_bounds(asset.obj_path)
    rel_lo = [lo[i] - com_local[i] for i in range(3)]
    rel_hi = [hi[i] - com_local[i] for i in range(3)]
    corners = [(scale * rel_lo[0], scale * rel_lo[1], scale * rel_lo[2]),
               (scale * rel_hi[0], scale * rel_hi[1], scale * rel_hi[2])]
    obj_extent = {
        "mesh_local_min": list(lo),
        "mesh_local_max": list(hi),
        "mesh_local_com": list(com_local),
        "half_extent_rel_com_m": [scale * (rel_hi[i] - rel_lo[i]) / 2.0
                                  for i in range(3)],
        "span_rel_com_m": [scale * (rel_hi[i] - rel_lo[i]) for i in range(3)],
        "origin_note": "position labels the CENTRE OF MASS in world space; the mesh "
                       "origin is placed at com - R(quat) @ (scale * mesh_local_com)",
    }
    print(f"[phyco] mesh local bounds {tuple(round(v,3) for v in lo)} .. "
          f"{tuple(round(v,3) for v in hi)} (scale {scale})", flush=True)
    traj = []
    for f in range(n_frames):
        p = annotation[str(f)][asset.name]["position"]
        for cx, cy, cz in corners:
            traj.append([p[0] + cx, p[1] + cy, p[2] + cz])
    if args.look in ("studio", "interior"):
        # Backdrop shots use the trajectory-aware framer, clamped to a distance
        # band.  A single fixed distance cannot serve both a 2.4 m circular
        # trajectory and an object that merely spins in place: the first needs
        # room, the second needs the lens close.  Auto-framing adapts per
        # scenario, the cap keeps the cyclorama/room in frame, and the floor stops
        # the camera crowding a very small subject.
        cam_dist, framing = pc.auto_frame_camera(
            kb, scene, traj, look_at,
            elevation_deg=args.camera_elevation, azimuth_deg=args.camera_azimuth,
            margin=args.camera_margin, start_distance=args.camera_distance,
            focal_length=args.focal_length, sensor_width=args.sensor_width,
            min_distance=args.camera_min_distance,
            max_distance=args.camera_max_distance,
        )
        framing["mode"] = f"{args.look}_auto_clamped"
    else:
        cam_dist, framing = pc.auto_frame_camera(
            kb, scene, traj, look_at,
            elevation_deg=args.camera_elevation, azimuth_deg=args.camera_azimuth,
            margin=args.camera_margin, start_distance=cam_dist or 5.0,
            focal_length=args.focal_length, sensor_width=args.sensor_width,
        )
    print(f"[phyco] camera framed d={cam_dist:.2f} "
          f"span=({framing.get('span_x', 0):.2f},{framing.get('span_y', 0):.2f}) "
          f"behind={framing.get('behind_camera', 0)}", flush=True)

    # ---- camera annotation -------------------------------------------------------------
    cam_info = kb.get_camera_info(scene.camera)
    camera_meta = {
        "position": [float(x) for x in scene.camera.position],
        "quaternion": [float(x) for x in scene.camera.quaternion],
        "focal_length": float(scene.camera.focal_length),
        "sensor_width": float(scene.camera.sensor_width),
        "field_of_view": float(scene.camera.field_of_view),
        "intrinsics": np.asarray(cam_info["K"]).tolist(),
        "extrinsics": np.asarray(cam_info["R"]).tolist(),
    }

    # ---- render ------------------------------------------------------------------------
    t_r = time.time()
    frames = list(range(n_frames))
    out = renderer.render(frames, return_layers=tuple(render_layers))
    # Kubric builds some layers with np.frombuffer over the EXR channel bytes, so
    # the returned arrays can be VIEWS over buffers whose lifetime is not tied to
    # the array.  Touching one after the backing object is collected is a
    # use-after-free that shows up as a hard segfault (observed in the depth
    # layer, in save_depth_png).  Take real copies immediately.
    out = {k: np.array(v, copy=True) for k, v in out.items()}
    render_secs = time.time() - t_r
    print(f"[phyco] rendered {n_frames} frames in {render_secs:.1f}s "
          f"({render_secs / max(n_frames, 1):.2f}s/frame)", flush=True)

    # Prepare every pixel buffer up front (pure numpy), then run the encoders.
    # DEPTH GOES FIRST: it is the layer whose backing buffer proved fragile, and
    # preparing rgba/segmentation before it reliably triggered a segfault.
    prepared = {}
    if "depth" in out:
        prepared["depth"] = pc.prepare_depth_mm(out["depth"])
    if "rgba" in out:
        prepared["rgba"] = pc.prepare_rgba(out["rgba"])
    if "segmentation" in out:
        prepared["segmentation"] = pc.prepare_segmentation(out["segmentation"])
    del out

    written = {}
    if "rgba" in prepared:
        # PNG keeps the frames lossless (the reference recipe); JPEG is offered
        # only as a space-saving option.
        if args.frame_format == "png":
            written["rgba"] = pc.write_image_sequence(
                prepared["rgba"], out_dir, "rgba", "png",
                [int(__import__("cv2").IMWRITE_PNG_COMPRESSION), 3])
        else:
            written["rgba"] = pc.write_image_sequence(
                prepared["rgba"], out_dir, "rgba", "jpg",
                [int(__import__("cv2").IMWRITE_JPEG_QUALITY), 95])
    if "segmentation" in prepared:
        written["segmentation"] = pc.write_image_sequence(
            prepared["segmentation"], out_dir, "segmentation", "png")
    if "depth" in prepared:
        written["depth"] = pc.write_image_sequence(
            prepared["depth"], out_dir, "depth", "png")

    videos = {}
    if args.save_mp4:
        if "rgba" in written:
            p = os.path.join(out_dir, "rgb.mp4")
            pat = f"rgba_%05d.{args.frame_format}"
            if pc.encode_video(out_dir, pat, p, args.frame_rate):
                videos["rgb"] = p
        if "segmentation" in written:
            p = os.path.join(out_dir, "segmentation.mp4")
            if pc.encode_video(out_dir, "segmentation_%05d.png", p, args.frame_rate):
                videos["segmentation"] = p
        if "depth" in written:
            p = os.path.join(out_dir, "depth.mp4")
            if pc.encode_video(out_dir, "depth_%05d.png", p, args.frame_rate):
                videos["depth"] = p
        print(f"[phyco] videos: {sorted(videos)}", flush=True)

    if args.qa_sheet:
        sheet = pc.make_qa_sheet(out_dir, n_frames)
        if sheet:
            print(f"[phyco] QA sheet: {os.path.basename(sheet)}", flush=True)

    # ---- metadata ----------------------------------------------------------------------
    meta = {
        "schema_version": "1.0",
        "video_id": video_id,
        "generator": "phyco-sim single_object",
        "scene": {
            "resolution": [res_w, res_h],
            "frame_start": 0,
            "frame_end": args.frame_end,
            "fps": args.frame_rate,
            "step_rate": args.step_rate,
            "num_frames": n_frames,
            "duration_s": (n_frames - 1) / fps,
            "gravity": list(gravity),
            "samples_per_pixel": args.samples,
            "denoising": not args.no_denoise,
            "layers": sorted(layers),
            "frame_format": args.frame_format,
            "lighting": backdrop_info,
            "seed": args.seed,
        },
        "camera": camera_meta,
        "camera_framing": framing,
        "object_extent": obj_extent,
        "motion": motion_meta,
        "simulation": sim_meta,
        "objects": [{
            "name": asset.name,
            "asset_id": asset.name,
            "mesh_obj": os.path.relpath(asset.obj_path, pc.PROJECT_ROOT),
            "mesh_urdf": os.path.relpath(asset.urdf_path, pc.PROJECT_ROOT),
            "scale": scale,
            "mass": 1.0,
            "friction": None,
            "restitution": None,
            "segmentation_id": 2,
            "static": False,
        }],
        "frames": annotation,
        "artifacts": {k: [os.path.basename(x) for x in v] for k, v in written.items()},
        "videos": {k: os.path.basename(v) for k, v in videos.items()},
        "timing": {"render_seconds": render_secs,
                   "render_seconds_per_frame": render_secs / max(n_frames, 1)},
    }
    pc.write_json(os.path.join(out_dir, "metadata.json"), meta)

    # Blender writes every frame as EXR + PNG into scratch_dir; without this the
    # temp tree grows by ~50 MB per video.
    try:
        import shutil
        shutil.rmtree(scratch, ignore_errors=True)
    except Exception:
        pass

    print(f"[phyco] DONE -> {out_dir}", flush=True)
    print(f"[phyco] frames written: "
          f"{ {k: len(v) for k, v in written.items()} }", flush=True)
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BaseException:
        # Blender swallows stderr on hard exits; persist the traceback next to the code.
        tb = traceback.format_exc()
        try:
            crash = os.path.join(pc.OUTCOMES_DIR, "_last_error.txt")
            os.makedirs(os.path.dirname(crash), exist_ok=True)
            with open(crash, "w", encoding="utf-8") as fh:
                fh.write(tb)
        except Exception:
            pass
        sys.stderr.write(tb)
        sys.stderr.flush()
        print("[phyco] FAILED:\n" + tb, flush=True)
        os._exit(1)
    print(f"[phyco] exit rc={rc}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc or 0)
