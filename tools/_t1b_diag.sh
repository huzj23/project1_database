#!/usr/bin/env bash
# ===========================================================================
# DECISIVE diagnostic: where does the rolling can's deceleration come from?
#
# The sweep showed the loss is roughly proportional to v0 (relchg 0.94-0.99 at
# every speed), which looks viscous rather than Coulomb.  This isolates it:
#   A  no spin, no friction   -> pure solver drag (any loss here is numerical)
#   B  spin,    no friction   -> friction removed, spin retained
#   C  spin,    mu 0.9        -> strong friction
#   D  no spin, mu 0.9        -> pure sliding
# and it queries the ACTUAL dynamics PyBullet holds (linear/angular damping,
# lateral/rolling/spinning friction) instead of trusting what we asked for.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - "$@" <<'PY'
import sys, math, copy
sys.path.insert(0, "src")
import numpy as np
from physim.config import load_run_config
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1001
base_cfg = load_run_config("configs/server.yaml", scenario="rolling_gso")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
asset = am.get("gso_whey_protein_vanilla")
ms = mm.get("replicad_apartment", require_files=True)

cfg = copy.deepcopy(base_cfg)
cfg["physics"] = {**cfg["physics"], "restitution_range": [0.0, 0.0]}
scen = create_scenario(cfg)
v = next(x for x in variants_from_config(cfg) if x.multiplier == 1.0)
smp0 = scen.sample(seed=seed, asset=asset, map_spec=ms, variant=v)

def variant_sample(friction=None, spin=True):
    d = smp0.to_dict()
    d.pop("variant", None)
    d["variant"] = smp0.variant
    if friction is not None:
        d["friction"] = friction
    if not spin:
        d["angular_velocity"] = (0.0, 0.0, 0.0)
    return type(smp0)(**d)

CASES = [
    ("A_nospin_nofric", 0.0,  False),
    ("B_spin_nofric",   0.0,  True),
    ("C_spin_mu0.9",    0.9,  True),
    ("D_nospin_mu0.9",  0.9,  False),
]
print(f"DIAG support_height={smp0.support_height:.6f} v0={np.linalg.norm(smp0.linear_velocity[:2]):.5f}")
print(f"DIAG omega0={list(np.round(smp0.angular_velocity,5))}")
for label, mu, spin in CASES:
    smp = variant_sample(mu, spin)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, asset)
    pos = np.asarray([s.position for s in res.trajectory], float)
    vel = np.asarray([s.linear_velocity for s in res.trajectory], float)
    om = np.asarray([s.angular_velocity for s in res.trajectory], float)
    t = np.asarray([s.time_seconds for s in res.trajectory], float)
    sp = np.linalg.norm(vel[:, :2], axis=1)
    travel = float(np.linalg.norm(pos[-1]-pos[0]))
    # local deceleration coefficient: d(ln v)/dt over the first half
    n = len(sp)//2
    good = sp[:n] > 1e-4
    if good.sum() > 5:
        k = -float(np.polyfit(t[:n][good], np.log(sp[:n][good]), 1)[0])
    else:
        k = float("nan")
    print(f"DIAG {label:16s} v0={sp[0]:.5f} v_end={sp[-1]:.5f} travel={travel:.4f} "
          f"lnv_decay_k={k:.4f} /s  omega_along_end={om[-1,1]:.4f}")

# ---- what dynamics does PyBullet ACTUALLY hold? --------------------------
import physim.reference as _ref
kb = _ref.load_phyco_kubric("third_party/phyco-sim")
from kubric.simulator import PyBullet as KbPyBullet
scene = kb.Scene(frame_start=1, frame_end=2, frame_rate=16, step_rate=240,
                 gravity=smp0.gravity)
sim = KbPyBullet(scene)
surface = ms.surface(smp0.surface_id)
sb = kb.FileBasedObject(name="surface_collision", asset_id="floor",
    simulation_filename=str(surface.collision_simulation_path),
    render_filename=None, scale=(1.0,1.0,1.0), static=True,
    friction=0.5, rolling_friction=0.0, spinning_friction=0.0,
    restitution=0.0, background=True, segmentation_id=1)
obj = kb.FileBasedObject(name="simulated_object", asset_id=asset.asset_id,
    simulation_filename=str(asset.collision.simulation_path),
    render_filename=None, scale=asset.scale, static=False, segmentation_id=2)
scene += [sb, obj]
obj.position = smp0.position
obj.quaternion = smp0.initial_quaternion
obj.mass = smp0.mass
obj.friction = 0.5
obj.rolling_friction = 0.0
obj.spinning_friction = 0.0
obj.restitution = 0.0
oid = obj.linked_objects[sim]
cl = sim._physics_client
cl.changeDynamics(oid, -1, mass=smp0.mass, lateralFriction=0.5,
                  rollingFriction=0.0, spinningFriction=0.0, restitution=0.0,
                  linearDamping=0.0, angularDamping=0.0)
d = cl.getDynamicsInfo(oid, -1)
names = ["mass","lateral_friction","local_inertia_diag","local_inertia_pos",
         "local_inertia_orn","restitution","rolling_friction","spinning_friction",
         "contact_damping","contact_stiffness","body_type","collision_margin"]
print("DIAG actual dynamics:")
for i, nm in enumerate(names):
    if i < len(d):
        print(f"DIAG   {nm} = {d[i]}")
print(f"DIAG urdf_origin_offset = {getattr(obj, 'urdf_origin_offset', None)}")
print("DIAG DONE")
PY
echo "RC DIAG DONE"
