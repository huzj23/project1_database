import numpy as np, os

R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"

def aabb(path):
    lo = np.array([1e18]*3); hi = np.array([-1e18]*3)
    n = 0
    with open(path, errors="ignore") as f:
        for line in f:
            if line.startswith("v "):
                p = np.array([float(x) for x in line.split()[1:4]])
                lo = np.minimum(lo, p); hi = np.maximum(hi, p); n += 1
    return lo, hi, n

def faces(path):
    n = 0
    with open(path, errors="ignore") as f:
        for line in f:
            if line.startswith("f "):
                n += 1
    return n

for aid in ["gso_whey_protein_vanilla", "gso_ecoforms_plant_container_gp16a_coral",
            "gso_room_essentials_fabric_cube_lavender", "gso_mad_gab_refresh_card_game",
            "gso_down_to_earth_orchid_pot_ceramic_lime", "gso_sootheze_cold_therapy_elephant"]:
    d = f"{R}/assets/objects/{aid}"
    v = f"{d}/visual/model.obj"
    c = f"{d}/collision/model.obj"
    if not os.path.exists(c):
        print(f"{aid}: NO collision/model.obj"); continue
    vlo, vhi, vn = aabb(v)
    clo, chi, cn = aabb(c)
    vd = vhi - vlo; cd = chi - clo
    same = np.allclose(vd, cd, atol=1e-4)
    print(f"{aid}")
    print(f"   visual   dim={np.round(vd,6).tolist()}  nv={vn} nf={faces(v)}")
    print(f"   collis   dim={np.round(cd,6).tolist()}  nv={cn} nf={faces(c)}")
    print(f"   same_frame_dims={same}  support_visual={-vlo[2]:.6f} support_collision={-clo[2]:.6f}")
