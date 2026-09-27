#!/usr/bin/env python
"""Mandated verification after the elephant rename + collision regeneration.

1. AssetManager loads special_plush_elephant; old id raises.
2. Both turntable scenarios sample at seed 5001, simulate, and validate.
3. Report camera framing for both, since bounding_radius feeds the camera
   solver's fallback radius.
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
from physim.camera import perpendicular_camera
from physim.pipeline import _camera_config

NEW = "special_plush_elephant"
OLD = "gso_sootheze_cold_therapy_elephant"

print("=" * 72)
print("STEP 1: AssetManager")
print("=" * 72)
am = AssetManager("configs/assets.yaml", "assets")
a = am.get(NEW)
print(f"  am.get({NEW!r})")
print(f"    collision.bounding_radius = {a.collision.bounding_radius}")
print(f"    collision.footprint_radius= {a.collision.footprint_radius}")
print(f"    collision.support_height  = {a.collision.support_height}")
print(f"    collision.triangles(manifest) = {a.metadata['collision'].get('triangles')}")
print(f"    collision.max_triangles   = {a.metadata['collision'].get('max_triangles')}")
print(f"    collision.mesh_sha256     = {a.metadata['collision'].get('mesh_sha256')}")
print(f"    category                  = {a.category}")
print(f"    a.support_height          = {a.support_height}")
print(f"    a.radius                  = {a.radius}")
print(f"    footprint <= bounding     : {a.collision.footprint_radius <= a.collision.bounding_radius}")

print()
print(f"  am.get({OLD!r}) must raise:")
try:
    am.get(OLD)
    print("    !!! FAIL: old id still resolves")
except KeyError as e:
    print(f"    KeyError OK: {str(e)[:100]}")
except Exception as e:
    print(f"    {type(e).__name__}: {str(e)[:100]}")

print()
print(f"  OLD id present in am.ids? {OLD in am.ids}")
print(f"  NEW id present in am.ids? {NEW in am.ids}")

print()
print("=" * 72)
print("STEP 2: turntable sampling + physics + validation at seed 5001")
print("=" * 72)
mm = MapManager("configs/maps.yaml", am)
ms = mm.get("replicad_apartment", require_files=True)

results = {}
for scen_name in ["turntable_carry_gso", "turntable_spin_gso"]:
    print()
    print("-" * 72)
    print(f"scenario config: {scen_name}")
    print("-" * 72)
    cfg = load_run_config("configs/server.yaml", scenario=scen_name)
    print(f"  selection.asset_ids = {cfg['selection']['asset_ids']}")
    # create_scenario REQUIRES the AssetManager kwarg for the turntable rig
    scen = create_scenario(cfg, asset_manager=am)
    v = variants_from_config(cfg)[0]
    print(f"  variant = {v.variant_id} ({v.variable} x{v.multiplier})")
    smp = scen.sample(seed=5001, asset=a, map_spec=ms, variant=v)
    print(f"  sample: surface={smp.surface_id} pos={tuple(round(x,4) for x in smp.position)}")
    print(f"          mass={smp.mass:.6f} radius={smp.radius:.6f} support_h={smp.support_height:.6f}")
    print(f"          support_asset={smp.support_asset_id} omega={smp.support_angular_velocity}")
    res = PyBulletBackend("third_party/phyco-sim").simulate(smp, ms, a)
    rep = validate_sample(res, smp, ms.surface(smp.surface_id), cfg["validation"])
    print(f"  validate_sample -> valid={rep.valid} reasons={list(rep.reasons)}")
    metrics = getattr(rep, "metrics", None) or {}
    for k in ["supported_fraction", "net_arc_degrees", "slip_ratio",
              "max_radial_displacement", "disc_rotation_degrees"]:
        if k in metrics:
            print(f"    {k} = {metrics[k]}")

    # --- camera framing (bounding_radius feeds the fallback radius) ---
    try:
        cam = perpendicular_camera(
            res, _camera_config(cfg, ms, smp), max_object_extent=object_extent(a)
        )
        f = cam.framing
        print(f"  camera: policy={cam.policy!r} position={tuple(round(x,4) for x in cam.position)}")
        print(f"          look_at={tuple(round(x,4) for x in cam.look_at)} "
              f"focal={cam.focal_length_mm}")
        print(f"          framing mode={f.get('mode')!r} distance={f.get('distance')}")
        print(f"          object_frame_fraction={f.get('object_frame_fraction')}")
        print(f"          content_width={f.get('content_width')} content_height={f.get('content_height')}")
        print(f"          max_object_extent={object_extent(a):.6f}")
    except Exception as e:
        print(f"  camera ERROR {type(e).__name__}: {str(e)[:200]}")
    results[scen_name] = (rep.valid, list(rep.reasons))

print()
print("=" * 72)
print("SUMMARY")
print("=" * 72)
for k, (valid, reasons) in results.items():
    print(f"  {k:24s} valid={valid} reasons={reasons}")
print(f"  bounding_radius={a.collision.bounding_radius} support_height={a.support_height} "
      f"category={a.category}")
