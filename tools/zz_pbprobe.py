"""Decisive: what frame does PyBullet put an OBJ collision mesh in?

Loads the SAME raw OBJ through a minimal URDF (identity origin) and prints the
world AABB PyBullet reports.  Compare with the file AABB.
"""
import pybullet as pb
import pybullet_data
import numpy as np
import os, tempfile, json

WS = "/data/raw/huzijian/project1_database"
REPO = f"{WS}/code/physics-video-sim/physics-video-sim-main"
RAW = f"{REPO}/assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj"
SC = f"{WS}/tmp/zz_pbprobe"
os.makedirs(SC, exist_ok=True)

def file_aabb(path):
    lo = np.array([1e18]*3); hi = np.array([-1e18]*3)
    for line in open(path, errors="ignore"):
        if line.startswith("v "):
            p = np.array([float(x) for x in line.split()[1:4]])
            lo = np.minimum(lo, p); hi = np.maximum(hi, p)
    return lo, hi

urdf = f"""<?xml version="1.0"?>
<robot name="probe">
  <link name="body">
    <inertial><origin xyz="0 0 0" rpy="0 0 0"/><mass value="1.0"/>
      <inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>
    <collision><origin xyz="0 0 0" rpy="0 0 0"/>
      <geometry><mesh filename="{RAW}" scale="1 1 1"/></geometry></collision>
  </link>
</robot>
"""
up = f"{SC}/probe.urdf"
open(up, "w").write(urdf)

cid = pb.connect(pb.DIRECT)
pb.setAdditionalSearchPath(pybullet_data.getDataPath())
bid = pb.loadURDF(up, useFixedBase=True)
print("body id:", bid)
# PyBullet's own collision AABB (uses its internal mesh frame)
aabb = pb.getAABB(bid, -1)
print("pybullet getAABB min:", np.round(aabb[0], 6).tolist())
print("pybullet getAABB max:", np.round(aabb[1], 6).tolist())
print("pybullet dims        :", np.round(np.array(aabb[1]) - np.array(aabb[0]), 6).tolist())

lo, hi = file_aabb(RAW)
print("file AABB min:", np.round(lo, 6).tolist())
print("file AABB max:", np.round(hi, 6).tolist())
print("file dims    :", np.round(hi - lo, 6).tolist())
pb.disconnect()
