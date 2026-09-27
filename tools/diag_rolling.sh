#!/usr/bin/env bash
# ===========================================================================
# DIAGNOSE rolling failure.
#
# Symptoms: travel_distance 0.068 m (needed 0.165), supported_fraction 0.012,
# max_speed 0.534 falling to ~0, speed_relative_change 0.9996.
#
# Suspects, in order:
#   1. the object is not ON the floor at all -- the collision mesh is the real
#      floor slab, whose top is at z ~ 0.0007, but `surface.position[2]` is
#      0.0007 and support_height is the object's half-height.  If the mesh's
#      top differs from position[2], the object either floats or starts buried.
#   2. friction is too high for a 1.4 g body -- lateralFriction 0.3-0.6 against
#      a 240 Hz solver can bleed a 0.5 m/s slide almost instantly.
#   3. the scenario's own angular_velocity = cross(n, v)/support_height gives a
#      huge spin for a SHORT object, and the contact then brakes hard.
#
# Measure each rather than guess.
# ===========================================================================
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

"$WS/tools/conda_env/bin/python" - <<'PY' 2>&1 | grep -E '^RG'
import sys, json, math
sys.path.insert(0, "src")
from physim.assets import AssetManager
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.config import load_run_config

def say(*a): print("RG", *a, flush=True)

cfg = load_run_config("configs/server.yaml")
am = AssetManager("configs/assets.yaml", "assets")
mm = MapManager("configs/maps.yaml", am)
scen = create_scenario(cfg)
asset = am.get("gso_whey_protein_vanilla")
ms = mm.get("replicad_apartment", require_files=True)

say(f"asset: {asset.asset_id}")
say(f"  support_height = {asset.support_height:.5f}")
say(f"  radius         = {asset.radius:.5f}")
say(f"  mass_range     = {asset.mass_range}")
say(f"  friction_range = {asset.friction_range}")
say(f"  restitution    = {asset.restitution_range}")
say(f"  collision type = {asset.collision.collision_type}")

for s in ms.surfaces:
    say(f"surface {s.surface_id}: position={s.position} bounds={s.bounds_xy}")
    say(f"  -> object centre z would be {s.position[2] + asset.support_height:.5f}")

v = next(x for x in variants_from_config(cfg) if x.multiplier == 1.0)
smp = scen.sample(seed=1001, asset=asset, map_spec=ms, variant=v)
say("")
say("sampled initial state:")
say(f"  position          = {tuple(round(x,5) for x in smp.position)}")
say(f"  linear_velocity   = {tuple(round(x,5) for x in smp.linear_velocity)}")
say(f"  angular_velocity  = {tuple(round(x,5) for x in smp.angular_velocity)}")
say(f"  |linear|          = {math.hypot(smp.linear_velocity[0], smp.linear_velocity[1]):.5f} m/s")
say(f"  |angular|         = {math.sqrt(sum(a*a for a in smp.angular_velocity)):.3f} rad/s")
say(f"  mass              = {smp.mass:.6f} kg")
say(f"  friction          = {smp.friction:.3f}")
say(f"  frame_count       = {smp.frame_count}  video_fps={smp.video_fps}")
say(f"  duration          = {smp.frame_count/smp.video_fps:.4f} s")
say("")
say(f"  travel needed     = {cfg['validation'].get('min_travel_object_extent_ratio',1.0)} x extent")
ext = max(asset.size) if asset.size else asset.radius*2
say(f"  object extent     = {ext:.5f}")
say(f"  implied min travel= {cfg['validation'].get('min_travel_object_extent_ratio',1.0)*ext:.5f}")
say("")
say(f"  expected travel if NO friction = {math.hypot(smp.linear_velocity[0],smp.linear_velocity[1]) * smp.frame_count/smp.video_fps:.5f} m")
PY
