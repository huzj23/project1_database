#!/usr/bin/env bash
# ===========================================================================
# FAST rolling-physics measurement harness (no rendering).
#
# Answers, by MEASUREMENT rather than assumption:
#   1. resting z vs surface.position[2] + support_height
#   2. is the long axis genuinely horizontal?
#   3. does it ROLL -- measured spin rate about the spin axis vs v/r
#      (slip ratio; 1.0 = rolling without slipping)
#   4. is the contact friction force non-zero?
#   5. forward roll or backspin (sign of the measured spin vs the travel dir)?
#
# Contact friction is read with the simulator's OWN physics-client proxy, the
# same way pybullet_backend._disc_contact does it, because module-level
# pybullet calls target client 0 and would read a stale world.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$@" <<'PY'
import sys, json, math
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.scenarios.common import object_extent
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

scenario_file = sys.argv[1] if len(sys.argv) > 1 else "rolling_gso"
asset_id = sys.argv[2] if len(sys.argv) > 2 else "gso_whey_protein_vanilla"
seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1001

cfg = load_run_config("configs/server.yaml", scenario=scenario_file)
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
scen = create_scenario(cfg)
asset = am.get(asset_id)
ms = mm.get("replicad_apartment", require_files=True)
v = next((x for x in variants_from_config(cfg) if x.multiplier == 1.0),
         variants_from_config(cfg)[0])
smp = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)
surf = ms.surface(smp.surface_id)

print(f"MEAS scenario={cfg['scenario']} asset={asset_id} seed={seed}")
print(f"MEAS orientation={json.dumps(smp.orientation, sort_keys=True)}")
print(f"MEAS surface.position={list(surf.position)}")
print(f"MEAS sample.support_height={smp.support_height:.6f} sample.radius={smp.radius:.6f}")
print(f"MEAS sample.initial_quaternion={list(smp.initial_quaternion)}")
print(f"MEAS sample.friction={smp.friction:.4f} mass={smp.mass:.6f}")
print(f"MEAS sample.angular_velocity={list(smp.angular_velocity)}")
print(f"MEAS sample.linear_velocity={list(smp.linear_velocity)}")
print(f"MEAS sample.position={list(smp.position)}")

def rot_from_quat_wxyz(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z),   2*(x*z+w*y)],
        [2*(x*y+w*z),   1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y),   2*(y*z+w*x),   1-2*(x*x+y*y)],
    ])
R0 = rot_from_quat_wxyz(smp.initial_quaternion)
local_z_world = R0 @ np.array([0.0, 0.0, 1.0])
print(f"MEAS long-axis(local Z) in world={np.round(local_z_world,6).tolist()} "
      f"|z|={abs(local_z_world[2]):.3e} -> horizontal={abs(local_z_world[2])<1e-6}")

backend = PyBulletBackend("third_party/phyco-sim")
res = backend.simulate(smp, ms, asset)
rep = validate_sample(res, smp, surf, cfg["validation"])

positions = np.asarray([s.position for s in res.trajectory], dtype=float)
vels = np.asarray([s.linear_velocity for s in res.trajectory], dtype=float)
omegas = np.asarray([s.angular_velocity for s in res.trajectory], dtype=float)
quats = np.asarray([s.quaternion for s in res.trajectory], dtype=float)

expected_z = float(surf.position[2]) + float(smp.support_height)
z_end = float(positions[-1, 2])
print(f"MEAS expected_z={expected_z:.6f} z_first={positions[0,2]:.6f} "
      f"z_end={z_end:.6f} |z_end-expected|={abs(z_end-expected_z)*1000:.3f} mm")
print(f"MEAS z_range=[{positions[:,2].min():.6f},{positions[:,2].max():.6f}] "
      f"span_mm={(positions[:,2].max()-positions[:,2].min())*1000:.3f}")
print(f"MEAS z_error_mm_max={np.abs(positions[:,2]-expected_z).max()*1000:.3f}")
print(f"MEAS z_tail10_mean={positions[-10:,2].mean():.6f}")

long_axis_z = []
for q in quats:
    R = rot_from_quat_wxyz(q)
    long_axis_z.append(abs(float((R @ np.array([0.0,0.0,1.0]))[2])))
long_axis_z = np.asarray(long_axis_z)
print(f"MEAS long-axis |world_z| over traj: max={long_axis_z.max():.6f} "
      f"-> stays horizontal={bool(long_axis_z.max() < 0.05)}")

planar_v = vels[:, :2]
d = planar_v[0] / max(np.linalg.norm(planar_v[0]), 1e-12)
spin_axis = np.array([-d[1], d[0], 0.0])
omega_along = omegas @ spin_axis
speed = np.linalg.norm(planar_v, axis=1)
r_eff = float(smp.support_height)
v_over_r = speed / r_eff
with np.errstate(divide="ignore", invalid="ignore"):
    slip = np.where(v_over_r > 1e-9, omega_along / v_over_r, np.nan)
mid = slice(len(speed)//4, 3*len(speed)//4)
print(f"MEAS spin_axis(world)={np.round(spin_axis,4).tolist()} travel_dir={np.round(d,4).tolist()}")
print(f"MEAS omega_along: first={omega_along[0]:.4f} mid={np.nanmean(omega_along[mid]):.4f} "
      f"last={omega_along[-1]:.4f} (rad/s)")
print(f"MEAS v/r        : first={v_over_r[0]:.4f} mid={np.nanmean(v_over_r[mid]):.4f} "
      f"last={v_over_r[-1]:.4f} (rad/s)")
print(f"MEAS slip_ratio : first={slip[0]:.4f} mid={np.nanmean(slip[mid]):.4f} "
      f"last={slip[-1]:.4f}  (1.0 = rolling without slipping)")
print(f"MEAS slip_mean_mid={np.nanmean(slip[mid]):.4f} slip_std_mid={np.nanstd(slip[mid]):.4f}")
print(f"MEAS sign_forward_roll={bool(np.nanmean(omega_along[mid]) > 0)}")
print(f"MEAS speed: first={speed[0]:.5f} mid={speed[len(speed)//2]:.5f} last={speed[-1]:.5f}")
print(f"MEAS travel_distance={float(np.linalg.norm(positions[-1]-positions[0])):.5f}")
print(f"MEAS max_speed_relative_change={rep.metrics.get('max_speed_relative_change')}")
print(f"MEAS supported_fraction={rep.metrics.get('supported_fraction')}")
print(f"MEAS trajectory_extent_object_ratio={rep.metrics.get('trajectory_extent_object_ratio')}")
print(f"MEAS VALID={rep.valid} reasons={list(rep.reasons)}")
print(f"MEAS collisions_recorded={len(res.collisions)}")

# ---- contact friction force, read from the simulator's own client ----------
import physim.reference as _ref
kb = _ref.load_phyco_kubric("third_party/phyco-sim")
from kubric.simulator import PyBullet as KbPyBullet
scene = kb.Scene(frame_start=1, frame_end=smp.frame_count,
                 frame_rate=smp.video_fps, step_rate=smp.physics_fps,
                 gravity=smp.gravity)
sim = KbPyBullet(scene)
surface = ms.surface(smp.surface_id)
support_body = kb.FileBasedObject(
    name="surface_collision", asset_id="floor",
    simulation_filename=str(surface.collision_simulation_path),
    render_filename=None, scale=(1.0,1.0,1.0), static=True,
    friction=smp.friction, rolling_friction=smp.rolling_friction,
    spinning_friction=smp.spinning_friction, restitution=smp.restitution,
    background=True, segmentation_id=1)
obj = kb.FileBasedObject(
    name="simulated_object", asset_id=asset.asset_id,
    simulation_filename=str(asset.collision.simulation_path),
    render_filename=None, scale=asset.scale, static=False, segmentation_id=2)
scene += [support_body, obj]
obj.position = smp.position
obj.quaternion = smp.initial_quaternion
obj.velocity = smp.linear_velocity
obj.angular_velocity = smp.angular_velocity
obj.mass = smp.mass
obj.friction = smp.friction
obj.rolling_friction = smp.rolling_friction
obj.spinning_friction = smp.spinning_friction
obj.restitution = smp.restitution
he = asset.collision.half_extents
inertia = (smp.mass*(he[1]**2+he[2]**2)/5.0, smp.mass*(he[0]**2+he[2]**2)/5.0,
           smp.mass*(he[0]**2+he[1]**2)/5.0)
oid = obj.linked_objects[sim]
sid = support_body.linked_objects[sim]
client = sim._physics_client
client.changeDynamics(oid, -1, mass=smp.mass, localInertiaDiagonal=inertia,
                      lateralFriction=smp.friction,
                      rollingFriction=smp.rolling_friction,
                      spinningFriction=smp.spinning_friction,
                      restitution=smp.restitution)
substeps = smp.physics_fps // smp.video_fps
normal_series, fric_series, up_series, fd_series = [], [], [], []
for f in range(smp.frame_count):
    nf, ff, up, fd = 0.0, 0.0, 0.0, [0.0, 0.0, 0.0]
    for _s in range(substeps):
        client.stepSimulation()
        for c in client.getContactPoints(bodyA=oid, bodyB=sid):
            if float(c[9]) <= 1e-9:
                continue
            if float(c[9]) > nf:
                nf = float(c[9])
                ff = math.hypot(float(c[10]), float(c[12]))
                fd = [float(v) for v in c[11]]
            up = max(up, abs(float(c[7][2])))
    normal_series.append(nf); fric_series.append(ff)
    up_series.append(up); fd_series.append(fd)
normal_series = np.asarray(normal_series); fric_series = np.asarray(fric_series)
weight = smp.mass * 9.81
print(f"MEAS contact frames with force>0: {int((normal_series>0).sum())}/{smp.frame_count}")
print(f"MEAS normal_force: mean={normal_series.mean():.6f} max={normal_series.max():.6f} N "
      f"(weight={weight:.6f} N, ratio={normal_series.mean()/max(weight,1e-12):.3f})")
print(f"MEAS friction_force: mean={fric_series.mean():.6f} max={fric_series.max():.6f} N "
      f"nonzero_frames={int((fric_series>1e-9).sum())}")
fd_arr = np.asarray(fd_series)
fric_proj = np.einsum("ij,j->i", fd_arr, np.array([d[0], d[1], 0.0]))
print(f"MEAS friction_dir.travel proj: mean={fric_proj.mean():.5f} "
      f"(negative = friction opposes travel, as it must for rolling)")
print(f"MEAS contact_normal_z: mean={np.asarray(up_series).mean():.4f}")
print("MEAS DONE")
PY
echo "RC ROLL MEASURE DONE"
