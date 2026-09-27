#!/usr/bin/env python
"""Confirm PyBullet loads the installed collision OBJ in the visual's frame.

PyBullet inflates a mesh's AABB by a uniform collision margin, so compare the
DIFFERENCES between axes (a rotation would permute them) and the uniform offset.
"""
import numpy as np
import pybullet as pb

REPO = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
EL = f"{REPO}/assets/objects/special_plush_elephant"


def aabb(path):
    lo = np.array([1e18] * 3)
    hi = np.array([-1e18] * 3)
    for line in open(path, errors="ignore"):
        if line.startswith("v "):
            v = np.array([float(x) for x in line.split()[1:4]])
            lo = np.minimum(lo, v)
            hi = np.maximum(hi, v)
    return lo, hi


def pb_aabb(path):
    cid = pb.connect(pb.DIRECT)
    bid = pb.loadURDF(path, useFixedBase=True)
    pmin, pmax = pb.getAABB(bid, -1)
    pb.disconnect()
    return np.array(pmin), np.array(pmax)


cases = [
    ("installed collision (aligned)", f"{EL}/collision/model.urdf", f"{EL}/collision/model.obj"),
    ("visual mesh itself", None, f"{EL}/visual/model.obj"),
]

for label, urdf, objpath in cases:
    if urdf is None:
        # wrap the visual in a throwaway URDF
        import os
        tmp = "/data/raw/huzijian/project1_database/tmp/zz_visprobe"
        os.makedirs(tmp, exist_ok=True)
        u = f"{tmp}/vis.urdf"
        open(u, "w").write(
            '<?xml version="1.0"?>\n<robot name="p"><link name="b">'
            '<inertial><origin xyz="0 0 0"/><mass value="1"/>'
            '<inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/></inertial>'
            f'<collision><origin xyz="0 0 0"/><geometry>'
            f'<mesh filename="{objpath}" scale="1 1 1"/></geometry></collision>'
            "</link></robot>\n"
        )
        urdf = u
    flo, fhi = aabb(objpath)
    plo, phi = pb_aabb(urdf)
    fd = fhi - flo
    pd = phi - plo
    print(f"--- {label}")
    print(f"    file dims     = {np.round(fd,6).tolist()}")
    print(f"    pybullet dims = {np.round(pd,6).tolist()}")
    print(f"    uniform offset (pb - file) = {np.round(pd - fd,6).tolist()}")
    print(f"    offsets identical across axes (=> no rotation): "
          f"{np.allclose(pd - fd, (pd - fd)[0], atol=1e-6)}")
    print(f"    axis order preserved: "
          f"{np.allclose(np.argsort(fd), np.argsort(pd))}")
