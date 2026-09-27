import numpy as np, sys, json

def load_obj(path):
    verts = []
    with open(path) as f:
        for line in f:
            if line.startswith('v '):
                parts = line.split()
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
    return np.array(verts, dtype=np.float64)

def report(name, path):
    v = load_obj(path)
    r3 = np.linalg.norm(v, axis=1)
    r2 = np.linalg.norm(v[:, :2], axis=1)
    lo = v.min(axis=0); hi = v.max(axis=0)
    he = np.maximum(np.abs(lo), np.abs(hi))
    print(f"--- {name}: {path}")
    print(f"    vertices={len(v)}")
    print(f"    min={lo.tolist()}")
    print(f"    max={hi.tolist()}")
    print(f"    half_extents_about_origin={he.tolist()}")
    print(f"    bounding_radius(max|v|)={r3.max():.9f}")
    print(f"    max_xy_radius={r2.max():.9f}")
    print(f"    support_height(-min_z)={-lo[2]:.9f}")
    print(f"    max(half_x,half_y)={max(he[0],he[1]):.9f}")

R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
report("food_lime collision", f"{R}/assets/objects/food_lime/collision/model.obj")
report("elephant collision (CURRENT 1968)", f"{R}/assets/objects/gso_sootheze_cold_therapy_elephant/collision/model.obj")
report("elephant visual (3.7MB)", f"{R}/assets/objects/gso_sootheze_cold_therapy_elephant/visual/model.obj")

print()
print("=== expected manifest values ===")
print("food_lime : bounding_radius=0.038384 footprint_radius=0.037884 support_height=0.030081 half_extents=[0.030008,0.030696,0.037712]")
print("elephant  : bounding_radius=0.202186 footprint_radius=0.133966 support_height=0.073659 half_extents=[0.133966,0.110335,0.103723]")
