#!/usr/bin/env python
"""Final consolidated verification."""
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, "src")

REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
NEW = "special_plush_elephant"
OLD = "gso_sootheze_cold_therapy_elephant"
EL = f"{REPO}/assets/objects/{NEW}"

print("=" * 74)
print("1. COLLISION MESH: triangle count and frame alignment")
print("=" * 74)


def aabb(path):
    lo = np.array([1e18] * 3)
    hi = np.array([-1e18] * 3)
    nv = nf = 0
    for line in open(path, errors="ignore"):
        if line.startswith("v "):
            v = np.array([float(x) for x in line.split()[1:4]])
            lo = np.minimum(lo, v)
            hi = np.maximum(hi, v)
            nv += 1
        elif line.startswith("f "):
            nf += 1
    return lo, hi, nv, nf


vlo, vhi, vnv, vnf = aabb(f"{EL}/visual/model.obj")
clo, chi, cnv, cnf = aabb(f"{EL}/collision/model.obj")
print(f"  visual    : nv={vnv} nf={vnf} dims={np.round(vhi-vlo,6).tolist()} support={-vlo[2]:.6f}")
print(f"  collision : nv={cnv} nf={cnf} dims={np.round(chi-clo,6).tolist()} support={-clo[2]:.6f}")
print(f"  triangles <= 512 : {cnf <= 512}  (actual {cnf})")
print(f"  support_height delta vs visual: {abs(-clo[2] - (-vlo[2])):.6f} m "
      f"({abs(-clo[2] - (-vlo[2])) / (-vlo[2]) * 100:.4f} %)")
print(f"  per-axis dim delta: {np.round(np.abs((chi-clo)-(vhi-vlo)),6).tolist()}")

print()
print("=" * 74)
print("2. PyBullet loads the installed URDF in the visual's frame")
print("=" * 74)
import pybullet as pb

urdf = f"{EL}/collision/model.urdf"
cid = pb.connect(pb.DIRECT)
bid = pb.loadURDF(urdf, useFixedBase=True)
pmin, pmax = pb.getAABB(bid, -1)
print(f"  pybullet AABB min={np.round(pmin,6).tolist()}")
print(f"  pybullet AABB max={np.round(pmax,6).tolist()}")
print(f"  pybullet dims   ={np.round(np.array(pmax)-np.array(pmin),6).tolist()}")
print(f"  collision file dims={np.round(chi-clo,6).tolist()}")
print(f"  PyBullet matches collision file dims: "
      f"{np.allclose(np.array(pmax)-np.array(pmin), chi-clo, atol=1e-4)}")
print(f"  (file dims were 0.269352/0.222324/0.209500 BEFORE this change)")
pb.disconnect()

print()
print("=" * 74)
print("3. Manifest fields required by the convention")
print("=" * 74)
import yaml

man = yaml.safe_load(open(f"{EL}/asset.yaml"))
col = man["collision"]
for k in ["mesh_sha256", "vertices", "triangles", "max_triangles",
          "bounding_radius", "support_height", "footprint_radius"]:
    print(f"  {k:18s} = {col.get(k)!r}")
print(f"  id                 = {man['id']!r}")
print(f"  category           = {man['category']!r}")
print(f"  license            = {man['license']!r}")
print(f"  source_sha256      = {man.get('source_sha256')!r}")
print(f"  source_page        = {man.get('source_page')!r}")
print(f"  footprint<=bounding: {col['footprint_radius'] <= col['bounding_radius']}")

print()
print("  replicad manifest:")
rman = yaml.safe_load(open(f"{REPO}/assets/environments/replicad_apartment/asset.yaml"))
print(f"    id            = {rman['id']!r}")
print(f"    license       = {rman['license']!r}")
print(f"    sha256        = {rman.get('sha256')!r}")
print(f"    source_sha256 = {rman.get('source_sha256')!r}")
print(f"    source_page   = {rman.get('source_page')!r}")
print(f"    physics.mass_range = {rman['physics']['mass_range']}")

print()
print("=" * 74)
print("4. AssetManager enumerates every asset; old id gone")
print("=" * 74)
from physim.assets import AssetManager

am = AssetManager("configs/assets.yaml", "assets")
print(f"  total assets: {len(am.ids)}")
for aid in am.ids:
    try:
        am.get(aid)
        ok = "OK"
    except Exception as e:
        ok = f"FAIL {type(e).__name__}: {str(e)[:60]}"
    print(f"    {aid:45s} {ok}")
print(f"  OLD id in ids: {OLD in am.ids}")
print(f"  NEW id in ids: {NEW in am.ids}")

print()
print("=" * 74)
print("5. datasets/ untouched?")
print("=" * 74)
n_old = subprocess.run(
    ["grep", "-rl", OLD, f"{REPO}/datasets"],
    capture_output=True, text=True,
).stdout.strip().splitlines()
print(f"  files under datasets/ still containing the OLD id: {len(n_old)}")
print(f"  (these are historical run records and MUST keep the old id)")
for f in n_old[:6]:
    print(f"    {f.replace(REPO + '/', '')}")
