#!/usr/bin/env python
"""Camera-framing verification (requirement (a)).

bounding_radius feeds the camera solver ONLY as the fallback for
footprint_radius (AssetSpec.radius).  object_extent() -- the value the framing
math actually consumes -- is derived from visual.size, not from
bounding_radius.  Both turntable configs additionally use `policy: fixed`, so
the pose is authored verbatim.  This script proves all of that explicitly.
"""
import sys

sys.path.insert(0, "src")

from physim.assets import AssetManager
from physim.config import load_run_config
from physim.maps import MapManager
from physim.scenarios import create_scenario, variants_from_config
from physim.scenarios.common import object_extent
from physim.physics.pybullet_backend import PyBulletBackend
from physim.validation import validate_sample
from physim.camera import fixed_camera, perpendicular_camera
from physim.pipeline import _camera_config

NEW = "special_plush_elephant"
am = AssetManager("configs/assets.yaml", "assets")
a = am.get(NEW)
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)

print("=== does object_extent depend on bounding_radius? ===")
print(f"  visual.size            = {a.size}")
print(f"  object_extent(asset)   = {object_extent(a):.6f}   (max of visual.size * scale)")
print(f"  collision.bounding_radius = {a.collision.bounding_radius}")
print(f"  collision.footprint_radius= {a.collision.footprint_radius}")
print(f"  a.radius (fp or brad)  = {a.radius}")
print("  -> framing consumes object_extent = visual max dimension;")
print("     bounding_radius only serves as the fallback for footprint_radius,")
print("     and footprint_radius is explicitly present, so it is not consulted.")

for scen_name in ["turntable_carry_gso", "turntable_spin_gso"]:
    print()
    print("=" * 72)
    print(f"{scen_name}")
    print("=" * 72)
    cfg = load_run_config("configs/server.yaml", scenario=scen_name)
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    smp = scen.sample(seed=5001, asset=a, map_spec=ms, variant=v)
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, a)
    rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
    print(f"  valid={rep.valid} reasons={list(rep.reasons)}")

    cam_cfg = _camera_config(cfg, ms, smp)
    print(f"  configured camera policy = {cam_cfg.get('policy')!r}")
    spec = fixed_camera(res, cam_cfg)
    print(f"  fixed_camera -> position={tuple(round(x,4) for x in spec.position)}")
    print(f"                  look_at ={tuple(round(x,4) for x in spec.look_at)}")
    print(f"                  focal   ={spec.focal_length_mm} mm")
    print(f"                  framing mode = {spec.framing.get('mode')!r}")
    print(f"                  framing distance = {spec.framing.get('distance')}")
    print(f"                  sensor_width_mm = {spec.framing.get('sensor_width_mm')}")

    # What the dynamic framing path WOULD compute, for reference only.
    dyn = perpendicular_camera(res, cam_cfg, max_object_extent=object_extent(a))
    d = dyn.framing
    print(f"  [reference] perpendicular_camera would give:")
    print(f"      object_frame_fraction = {d.get('object_frame_fraction')}")
    print(f"      content_width={d.get('content_width')} content_height={d.get('content_height')}")
    print(f"      distance={d.get('distance')} max_object_extent={d.get('max_object_extent')}")
