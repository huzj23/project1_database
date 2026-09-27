import numpy as np, sys

def aabb(path):
    lo = np.array([1e18]*3); hi = np.array([-1e18]*3); nv = nf = 0
    for line in open(path, errors="ignore"):
        if line.startswith("v "):
            p = np.array([float(x) for x in line.split()[1:4]])
            lo = np.minimum(lo, p); hi = np.maximum(hi, p); nv += 1
        elif line.startswith("f "):
            nf += 1
    return lo, hi, nv, nf

WS = "/data/raw/huzijian/project1_database"
REPO = f"{WS}/code/physics-video-sim/physics-video-sim-main"
print("=== TEST OUTPUT of generator on the elephant visual (as specified) ===")
lo, hi, nv, nf = aabb(f"{WS}/tmp/zz_coll_test/model.obj")
print(f"  nv={nv} nf={nf}")
print(f"  min={np.round(lo,6).tolist()} max={np.round(hi,6).tolist()}")
print(f"  dims={np.round(hi-lo,6).tolist()}  support_height={-lo[2]:.6f}")

print("=== COMMITTED elephant collision mesh (1968 tris) ===")
lo2, hi2, nv2, nf2 = aabb(f"{REPO}/assets/objects/gso_sootheze_cold_therapy_elephant/collision/model.obj")
print(f"  nv={nv2} nf={nf2}")
print(f"  min={np.round(lo2,6).tolist()} max={np.round(hi2,6).tolist()}")
print(f"  dims={np.round(hi2-lo2,6).tolist()}  support_height={-lo2[2]:.6f}")

print("=== ELEPHANT visual (raw file) ===")
lo3, hi3, nv3, nf3 = aabb(f"{REPO}/assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj")
print(f"  dims={np.round(hi3-lo3,6).tolist()}  support_height={-lo3[2]:.6f}")
