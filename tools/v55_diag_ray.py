from pathlib import Path
import numpy as np, trimesh
R = Path("/data/raw/huzijian/project1_database/outcomes/v55/scenes/italian_flat")
vis = trimesh.load(str(R/"runtime/Bicchiere_Cristallo_visual.obj"), process=True, force="mesh")
parts = sorted((R/"props").glob("glass_a_part*.obj"))
print("parts", len(parts))
origins = np.array([[0.5,0,0.0],[0,0.5,0.0],[0,0,0.5]])
dirs = -origins/np.linalg.norm(origins,axis=1,keepdims=True)
try:
    loc, iray, itri = vis.ray.intersects_location(origins, dirs, multiple_hits=False)
    print("visual ray OK: hits", len(loc))
except Exception as e:
    print("visual ray RAISED", type(e).__name__, e)
ms = [trimesh.load(str(f), process=True, force="mesh") for f in parts]
mesh = trimesh.util.concatenate(ms)
try:
    loc2, iray2, itri2 = mesh.ray.intersects_location(origins, dirs, multiple_hits=False)
    print("proxy ray OK: hits", len(loc2))
    print("engine:", type(mesh.ray).__name__)
except Exception as e:
    print("proxy ray RAISED", type(e).__name__, e)
