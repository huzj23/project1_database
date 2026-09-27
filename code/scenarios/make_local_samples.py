"""Local realism samples: GSO scanned actor + PBR ground + HDRI + shadow tuning.

Runs under Blender's own interpreter (bpy is only available there):

    blender.exe --background --factory-startup \
        --python code/scenarios/make_local_samples.py -- \
        --outcomes outcomes/_本地样本 --preset ab

Deliverable per sample: lossless PNG frames + a QA contact sheet, so a human can
pick the lighting/shadow setting before committing GPU-server time.

Design notes
------------
* Actor: a real scanned GSO object, `position.z = -bounds.min_z` puts it exactly
  on the floor (no floating).
* Ground: PBR concrete with `uv_scale` chosen so texel density matches the
  on-screen resolution -- this is what fixed the blurry background.
* Background + light: a Poly Haven 4K HDRI.  A separate softbox provides the
  contact shadow, and the HDRI ambient strength is a *tunable* because too much
  ambient washes the shadow out entirely.
* Material: the actor keeps its imported `.mtl` (4096^2 texture); overriding
  `obj.material` would replace it with a flat colour.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import phyco_common as pc  # noqa: E402
import phyco_motions as pm  # noqa: E402
import phyco_backdrops as pb  # noqa: E402

pc.bootstrap_syspath()
pc.patch_numpy_legacy_aliases()

import numpy as np  # noqa: E402
import kubric as kb  # noqa: E402
from kubric.simulator import PyBullet  # noqa: E402
from kubric.renderer import Blender  # noqa: E402


# --------------------------------------------------------------------------------------
# Sample grid
# --------------------------------------------------------------------------------------

#: (tag, ambient, key, key_kind, note)
#: key_kind: "sun" gives a crisp, legible shadow; "area" gives a soft studio
#: shadow.  A large area light close to a small subject produces almost pure
#: penumbra, which is why the earlier softbox left the floor looking shadowless.
LIGHT_GRID = [
    ("sun_amb_low",  0.05, 5.0,   "sun",  "crisp contact shadow, HDRI still visible"),
    ("sun_amb_mid",  0.15, 5.0,   "sun",  "a little fill, shadow still readable"),
    ("area_amb_low", 0.05, 400.0, "area", "soft studio shadow, no hard edge"),
]

#: (tag, gso object, motion)
ACTOR_GRID = [
    ("elephant", "Sootheze_Cold_Therapy_Elephant", "circular"),
    ("cube",     "Room_Essentials_Fabric_Cube_Lavender", "damped"),
]

#: Backdrop comparison: the same actor and lighting, only the environment differs.
#: (tag, backdrop, ambient, key, key_kind, note)
BACKDROP_GRID = [
    ("wh",     "warehouse", 0.05, 5.0, "sun",
     "HDRI warehouse backdrop + PBR concrete ground"),
    ("in_lo",  "interior",  0.05, 5.0, "sun",
     "ReplicaCAD room; same lighting as the warehouse shot"),
    ("in_mid", "interior",  0.25, 5.0, "sun",
     "ReplicaCAD room with more indirect fill (rooms are dimmer than outdoors)"),
    ("in_soft", "interior", 0.50, 2.2, "sun",
     "indoor-like: softer sun through a window, stronger bounce"),
]

#: where the actor sits inside a ReplicaCAD room (metres, room-local x/y)
INTERIOR_ANCHOR = (1.0, -3.0)

#: world size of the ground plate and the PBR tiling
GROUND_M = 8.0
UV_SCALE = 8.0     # 4K over 8 m -> 4096 texel/m


#: GSO actors for the main "real object" track.  All are between 12 and 30 cm,
#: roughly isotropic, and single objects (the library also holds multi-part sets
#: named *_SET, which are unsuitable as one moving body).
SERVER_ACTORS = [
    "Sootheze_Cold_Therapy_Elephant",
    "Room_Essentials_Fabric_Cube_Lavender",
    "Mad_Gab_Refresh_Card_Game",
    "Ecoforms_Plant_Container_GP16A_Coral",
    "Down_To_Earth_Orchid_Pot_Ceramic_Lime",
    "Whey_Protein_Vanilla",
]

#: (motion, [(tag suffix, params), ...]) -- two variants per family
#: (motion, [(tag suffix, params), ...]) -- amplitudes are multiples of the
#: actor's own size, so framing stays consistent across a 12-29 cm object range.
SERVER_MOTIONS = [
    ("circular", [("r075_p50", {"radius_k": 0.75, "period": 5.0}),
                  ("r110_p35", {"radius_k": 1.10, "period": 3.5})]),
    ("damped",   [("t25_k055", {"travel_k": 2.5, "damping": 0.55}),
                  ("t38_k085", {"travel_k": 3.8, "damping": 0.85})]),
    ("rotation", [("az_p40", {"axis": "z", "period": 4.0}),
                  ("ay_p30", {"axis": "y", "period": 3.0})]),
]


def server_d_jobs():
    """Track D: the same actors inside a real ReplicaCAD room.

    Deliberately small -- this is a probe batch to judge whether the interior
    route is worth scaling, not a full delivery.  Lighting is the indoor balance
    (soft key + stronger bounce) because a hard sun reads wrong inside.
    """
    jobs = []
    for gso in ("Sootheze_Cold_Therapy_Elephant",
                "Room_Essentials_Fabric_Cube_Lavender",
                "Ecoforms_Plant_Container_GP16A_Coral"):
        for motion, vtag, params in (
                ("circular", "r075_p50", {"radius_k": 0.75, "period": 5.0}),
                ("damped", "t25_k055", {"travel_k": 2.5, "damping": 0.55}),
                ("rotation", "az_p40", {"axis": "z", "period": 4.0})):
            tag = f"D_{motion}_{short_name(gso)}_{vtag}"
            jobs.append((tag, gso, motion, params))
    return jobs


def short_name(gso: str) -> str:
    """Compact, filesystem-safe actor tag."""
    s = gso.lower().replace("_", "")
    for junk in ("soothezecoldtherapy", "roomeessentials", "madgabrefresh",
                 "ecoformsplantcontainer", "downtoearthorchidpotceramic",
                 "wheyprotein"):
        s = s.replace(junk, "")
    return (s or gso.lower())[:18]


def server_a_jobs():
    """Full job list for the server main track (6 actors x 3 motions x 2 = 36)."""
    jobs = []
    for gso in SERVER_ACTORS:
        for motion, variants in SERVER_MOTIONS:
            for vtag, params in variants:
                tag = f"{motion}_{short_name(gso)}_{vtag}"
                jobs.append((tag, gso, motion, params))
    return jobs


def gso_asset(name: str):
    """Resolve a GSO object into (obj, urdf, bounds, mass, rest_z)."""
    d = os.path.join(pb.GSO_ROOT, name)
    dj = os.path.join(d, "data.json")
    if not os.path.isfile(dj):
        raise FileNotFoundError(f"GSO object not synced locally: {dj}")
    meta = json.load(open(dj))
    b = meta["kwargs"]["bounds"]
    return (os.path.join(d, "visual_geometry.obj"),
            os.path.join(d, "object.urdf"),
            b, meta["kwargs"]["mass"], -b[0][2])


def build_sample(tag, gso_name, motion, backdrop, ambient, key_w, key_kind, out_dir,
                 resolution, samples, n_frames, fps, seed, params=None,
                 probe_only=False):
    params = params or {}
    obj_path, urdf_path, b, mass, rest_z = gso_asset(gso_name)
    span = [b[1][i] - b[0][i] for i in range(3)]

    scratch = pc.tempfile.mkdtemp(prefix="ls_")
    scene = kb.Scene(resolution=resolution, frame_start=0, frame_end=n_frames - 1,
                     frame_rate=fps, step_rate=240, gravity=(0, 0, 0))
    renderer = Blender(scene, scratch, samples_per_pixel=samples,
                       use_denoising=True, verbose=True)
    sim = PyBullet(scene, scratch)

    # --- environment ----------------------------------------------------------
    info = {"backdrop": backdrop}
    if backdrop == "interior":
        # Photoreal ReplicaCAD room via the *direct* bpy glTF import.  Kubric's
        # own glTF path overwrites the node transforms and throws the room
        # hundreds of metres away (see phyco_backdrops.add_stage_direct).
        ax, ay = INTERIOR_ANCHOR
        room = pb.add_stage_direct(
            renderer,
            os.path.join(pb.REPLICAD_ROOT, "stages", "frl_apartment_stage.glb"))
        info.update(room)
        # Use the floor height AT the anchor, not the room's global minimum:
        # ReplicaCAD floors are not level, and the global min sits below the
        # floorboards at most places (it sinks the actor half into the floor).
        local = pb.floor_z_at(renderer, ax, ay)
        floor_z = local if local is not None else room["floor_z"]
        info["floor_z_global"] = room["floor_z"]
        info["floor_z_local"] = floor_z
        # the room's own floor is the ground, so no PBR plate is added
    else:
        ax = ay = 0.0
        floor_z = 0.0
        ground = kb.Cube(name="ground", scale=(GROUND_M / 2, GROUND_M / 2, 0.1),
                         position=(0, 0, -0.1), static=True, segmentation_id=1)
        ground.material = kb.PrincipledBSDFMaterial(color=(0.55, 0.55, 0.55, 1.0),
                                                    roughness=0.85)
        scene += ground
        mat, _mi = pb.pbr_material(kb, "concrete_floor_worn_001", "concrete_textures",
                                   uv_scale=UV_SCALE)
        pb.apply_bpy_material(renderer, ground, mat)
        info["ground"] = {"pbr": "concrete_floor_worn_001",
                          "texel_per_m": 4096 * UV_SCALE / GROUND_M}

    # --- background + ambient light ------------------------------------------
    # The HDRI stays fully visible to the camera while contributing very little
    # fill light; a bright ambient floods the floor and erases the shadow.
    hdri_path = pb.enable_hdri_file(renderer, "empty_warehouse_01",
                                   strength=ambient, bg_strength=1.0)
    info["hdri"] = {"id": "empty_warehouse_01", "ambient": ambient, "bg": 1.0}

    # --- actor resting on the floor -------------------------------------------
    # `position.z = floor_z + rest_z` puts the object's lowest point exactly on
    # the floor -- this is what removes the "floating" look.
    base_z = floor_z + rest_z
    obj = kb.FileBasedObject(
        name=gso_name, simulation_filename=urdf_path, render_filename=obj_path,
        bounds=tuple(tuple(v) for v in b), mass=mass, scale=1.0,
        position=(ax, ay, base_z), segmentation_id=2)
    scene += obj            # keep the imported .mtl texture -- do not override

    # --- motion, hugging the floor -------------------------------------------
    # The motion amplitude is derived from the ACTOR's own size rather than fixed
    # in metres.  GSO objects span 12-29 cm, so an absolute radius frames a small
    # pot as a speck and a large plush toy tightly.  Holding (object/trajectory)
    # roughly constant yields consistent framing -- and therefore a consistent
    # subject size on screen -- across the whole library.
    obj_size = max(span)
    mscale = params.get("motion_scale", 1.0)

    if motion == "circular":
        radius = params.get("radius_k", 0.75) * obj_size * mscale
        spec = pm.CircularSpec(radius=radius,
                               period_s=params.get("period", 5.0),
                               center=(ax, ay, base_z), axis="z",
                               spin_per_orbit=1.0)
        states = pm.apply_circular(kb, obj, spec, n_frames, float(fps),
                                   [0.0, 0.0, 0.0])
        applied = {"radius_m": round(radius, 4), "period_s": spec.period_s,
                   "tangential_speed": round(spec.tangential_speed, 4)}
    elif motion == "rotation":
        spec = pm.RotationSpec(axis=params.get("axis", "z"),
                               period_s=params.get("period", 4.0),
                               angular_damping=params.get("angular_damping", 0.0),
                               center=(ax, ay, base_z))
        states = pm.apply_rotation(kb, obj, spec, n_frames, float(fps),
                                   [0.0, 0.0, 0.0])
        applied = {"axis": spec.axis, "period_s": spec.period_s}
    else:
        damping = params.get("damping", 0.55)
        travel = params.get("travel_k", 2.5) * obj_size * mscale
        speed = travel * damping          # travel == speed / damping
        spec = pm.DampedSpec(speed=speed,
                             direction_deg=params.get("direction_deg", 0.0),
                             linear_damping=damping,
                             angular_damping=0.9, spin_rate=1.5,
                             start=(ax, ay, base_z))
        states = pm.apply_damped(kb, obj, spec, n_frames, float(fps),
                                 [0.0, 0.0, 0.0])
        applied = {"speed": round(speed, 4), "damping": damping,
                   "travel_m": round(travel, 4)}

    aim = (ax, ay, base_z)

    # --- key light: supplies the readable contact shadow ----------------------
    # Placed opposite the camera so the shadow stretches *across* frame; a light
    # behind the camera drops the shadow directly under the subject where the
    # body hides it.
    if key_kind == "sun":
        # A distant directional light: parallel rays => a crisp, unambiguous
        # shadow, and the classic way product shots read as "grounded".
        key = kb.DirectionalLight(name="Key", position=(ax - 2.4, ay - 1.1, base_z + 2.2),
                                  intensity=key_w, color=(1.0, 0.97, 0.92))
        key.look_at(aim)
    else:
        # Small and close: a big softbox far away yields pure penumbra.
        key = kb.RectAreaLight(name="Key", position=(ax - 0.9, ay - 0.45, base_z + 0.85),
                               intensity=key_w, width=0.5, height=0.5,
                               color=(1.0, 0.97, 0.92))
        key.look_at(aim)
    scene += key

    # --- fill from the camera side -------------------------------------------
    # Lifts the camera-facing side that the key leaves in shade, without washing
    # the shadow out.
    fill = kb.RectAreaLight(name="Fill", position=(ax + 1.1, ay - 1.0, base_z + 1.1),
                            intensity=(key_w * 0.08 if key_kind == "sun" else 120.0),
                            width=0.8, height=0.8, color=(0.95, 0.97, 1.0))
    fill.look_at(aim)
    scene += fill

    # --- framing: subject + its path, no clamps -------------------------------
    traj = []
    h = span[2] / 2.0
    for f in range(n_frames):
        p = states[f]["position"]
        for dx, dy, dz in ((0, 0, h), (0, 0, -h),
                           (span[0] / 2, 0, 0), (-span[0] / 2, 0, 0)):
            traj.append([p[0] + dx, p[1] + dy, p[2] + dz])
    # Inside a room the subject sits on the floor and the camera is close, so a
    # high elevation shows nothing but floorboards.  A flatter angle brings the
    # walls, doorways and staircase into frame -- that context is the whole
    # reason to use a real 3D interior instead of an HDRI.
    elev = 11.0 if backdrop == "interior" else 20.0
    aim_frac = 0.35 if backdrop == "interior" else 0.5
    cam_d, fr = pc.auto_frame_camera(
        kb, scene, traj, (ax, ay, base_z + span[2] * aim_frac),
        elevation_deg=elev, azimuth_deg=-62.0, margin=0.16,
        start_distance=1.6, focal_length=55.0, sensor_width=36.0)
    vis_w = 2 * cam_d * np.tan(np.arctan(36 / (2 * 55.0)))

    # Trajectory extent on the floor, as a multiple of the actor's own size.  A
    # low ratio means the subject reads large; a high one means it is lost in its
    # own motion.  Printed so framing can be checked without rendering.
    pos = np.array([states[f]["position"] for f in range(n_frames)], dtype=float)
    traj_span = float(np.hypot(pos[:, 0].ptp(), pos[:, 1].ptp()))
    ratio = traj_span / max(span[0], 1e-6)

    if probe_only:
        pct = float(100 * span[0] / vis_w)
        print(f"[sample] {tag}: d={cam_d:.2f}m actor={pct:.0f}% frame  "
              f"mover={motion} traj={traj_span:.2f}m traj/obj={ratio:.2f}", flush=True)
        return {
            "tag": tag, "gso_object": gso_name, "motion": motion,
            "backdrop": backdrop, "probe_only": True,
            "actor_span_m": span, "motion_applied": applied,
            "trajectory_span_m": round(traj_span, 4),
            "traj_over_object": round(ratio, 3),
            "camera_distance_m": float(cam_d),
            "actor_pct_of_frame_width": pct,
        }

    bpy = __import__("bpy")
    bpy.context.scene.render.use_motion_blur = True
    bpy.context.scene.render.motion_blur_shutter = 0.25

    out = renderer.render(list(range(n_frames)),
                          return_layers=("rgba", "segmentation", "depth"))
    out = {k: np.array(v, copy=True) for k, v in out.items()}
    prepared = {"depth": pc.prepare_depth_mm(out["depth"]),
                "rgba": pc.prepare_rgba(out["rgba"]),
                "segmentation": pc.prepare_segmentation(out["segmentation"])}

    sdir = os.path.join(out_dir, tag)
    pc.write_image_sequence(prepared["rgba"], sdir, "rgba", "png")
    pc.write_image_sequence(prepared["segmentation"], sdir, "segmentation", "png")
    pc.write_image_sequence(prepared["depth"], sdir, "depth", "png")
    pc.make_qa_sheet(sdir, n_frames)

    # Preview videos.  The PNGs stay the source of truth (a 96-frame run is ~95 MB
    # of lossless frames but only ~1 MB as CRF-16 H.264), so reviewers get
    # something they can actually watch without shipping the frames around.
    videos = {}
    for layer, out_name in (("rgba", "rgb.mp4"), ("depth", "depth.mp4"),
                            ("segmentation", "segmentation.mp4")):
        tgt = os.path.join(sdir, out_name)
        if pc.encode_video(sdir, f"{layer}_%05d.png", tgt, float(fps)):
            videos[layer] = out_name

    meta = {
        "tag": tag, "gso_object": gso_name, "motion": motion,
        "backdrop": backdrop,
        "resolution": list(resolution), "frames": n_frames, "fps": fps,
        "samples_per_pixel": samples,
        "ambient_hdri_strength": ambient, "key_intensity": key_w, "key_kind": key_kind,
        "actor_span_m": span, "actor_rest_z": rest_z, "floor_z": floor_z,
        "motion_params": params, "motion_applied": applied,
        "trajectory_span_m": round(traj_span, 4),
        "traj_over_object": round(ratio, 3),
        "camera_distance_m": float(cam_d),
        "actor_pct_of_frame_width": float(100 * span[0] / vis_w),
        "material": "GSO imported .mtl (texture.png) preserved",
        "videos": videos,
    }
    if backdrop == "interior":
        meta["room"] = {"stage": info.get("stage"), "extents_m": info.get("extents_m"),
                        "meshes": info.get("meshes")}
    else:
        meta["ground"] = {"pbr": "concrete_floor_worn_001", "size_m": GROUND_M,
                          "texel_per_m": 4096 * UV_SCALE / GROUND_M}
    pc.write_json(os.path.join(sdir, "sample.json"), meta)
    print(f"[sample] {tag}: d={cam_d:.2f}m actor={meta['actor_pct_of_frame_width']:.0f}% "
          f"frame  backdrop={backdrop} ambient={ambient} key={key_w:.0f} {key_kind}",
          flush=True)
    return meta


def main(argv):
    ap = argparse.ArgumentParser(prog="make_local_samples")
    ap.add_argument("--outcomes", default=os.path.join(pc.OUTCOMES_DIR, "_本地样本"))
    ap.add_argument("--resolution", default="640x360")
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--frames", type=int, default=32)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--preset", default="ab",
                    choices=["ab", "backdrop", "server_a", "server_d"],
                    help="ab = lighting study; backdrop = environment comparison")
    ap.add_argument("--only", default=None, help="substring filter on the sample tag")
    ap.add_argument("--shard_index", type=int, default=0,
                    help="this process takes jobs where (i %% shard_total) == shard_index")
    ap.add_argument("--shard_total", type=int, default=1)
    ap.add_argument("--dry_run", action="store_true")
    ap.add_argument("--no_skip_existing", action="store_true",
                    help="re-render even if sample.json already exists")
    ap.add_argument("--probe_only", action="store_true",
                    help="set the scene up and report framing without rendering")
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    args = ap.parse_args(argv)

    res = pc.parse_resolution(args.resolution)
    os.makedirs(args.outcomes, exist_ok=True)
    # Resumable by default: a crashed or interrupted batch can simply be re-run
    # and it will fill only the gaps.
    skip_existing = not args.no_skip_existing

    metas = []
    if args.preset in ("server_a", "server_d"):
        backdrop = "interior" if args.preset == "server_d" else "warehouse"
        # indoor balance: a hard sun reads wrong inside, so soften it and lift
        # the bounce (the same reasoning behind variant D in the backdrop study)
        ambient = 0.50 if backdrop == "interior" else 0.05
        key_w = 2.2 if backdrop == "interior" else 5.0
        # Main track: warehouse HDRI backdrop (approved), across the GSO actor
        # set, the three motion families and two parameter variants each.
        jobs = server_d_jobs() if args.preset == "server_d" else server_a_jobs()
        jobs = [j for i, j in enumerate(jobs) if i % args.shard_total == args.shard_index]
        print(f"[sample] {args.preset}: {len(jobs)} jobs in shard "
              f"{args.shard_index}/{args.shard_total}", flush=True)
        for tag, gso, motion, params in jobs:
            if args.only and args.only not in tag:
                continue
            if skip_existing and os.path.isfile(
                    os.path.join(args.outcomes, tag, "sample.json")):
                print(f"[sample] skip (already done): {tag}", flush=True)
                continue
            if args.dry_run:
                print(f"[sample] would render {tag}  ({gso}, {motion}, {params})")
                continue
            t0 = time.time()
            m = build_sample(tag, gso, motion, backdrop, ambient, key_w, "sun",
                             args.outcomes, res, args.samples, args.frames,
                             args.fps, args.seed, params, args.probe_only)
            m["seconds"] = round(time.time() - t0, 1)
            metas.append(m)
    elif args.preset == "backdrop":
        # Same actor + lighting, only the environment changes -- this is the
        # comparison that decides which backdrop to scale up on the server.
        actor_tag, gso, motion = ACTOR_GRID[0]
        for b_tag, backdrop, ambient, key_w, key_kind, _note in BACKDROP_GRID:
            tag = f"{actor_tag}__{b_tag}"
            if args.only and args.only not in tag:
                continue
            if args.dry_run:
                print(f"[sample] would render {tag}  ({gso}, {motion}, "
                      f"backdrop={backdrop}, ambient={ambient}, key={key_w:.0f} {key_kind})")
                continue
            t0 = time.time()
            m = build_sample(tag, gso, motion, backdrop, ambient, key_w, key_kind,
                             args.outcomes, res, args.samples, args.frames,
                             args.fps, args.seed, {})
            m["seconds"] = round(time.time() - t0, 1)
            metas.append(m)
    else:
        for a_tag, gso, motion in ACTOR_GRID:
            for l_tag, ambient, key_w, key_kind, _note in LIGHT_GRID:
                tag = f"{a_tag}__{l_tag}"
                if args.only and args.only not in tag:
                    continue
                if args.dry_run:
                    print(f"[sample] would render {tag}  ({gso}, {motion}, "
                          f"ambient={ambient}, key={key_w:.0f} {key_kind})")
                    continue
                t0 = time.time()
                m = build_sample(tag, gso, motion, "warehouse", ambient, key_w,
                                 key_kind, args.outcomes, res, args.samples,
                                 args.frames, args.fps, args.seed, params)
                m["seconds"] = round(time.time() - t0, 1)
                metas.append(m)

    if metas:
        pc.write_json(os.path.join(args.outcomes, "samples_index.json"),
                      {"count": len(metas), "samples": metas})
    print(f"[sample] done: {len(metas)} samples -> {args.outcomes}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        rc = main(sys.argv)
    except BaseException:
        import traceback
        tb = traceback.format_exc()
        try:
            with open(os.path.join(pc.OUTCOMES_DIR, "_last_error.txt"), "w",
                      encoding="utf-8") as fh:
                fh.write(tb)
        except Exception:
            pass
        print("[sample] FAILED:\n" + tb, flush=True)
        os._exit(1)
    print(f"[sample] exit rc={rc}", flush=True)
    os._exit(rc or 0)
