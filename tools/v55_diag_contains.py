from pathlib import Path
import numpy as np, trimesh
P = Path("/data/raw/huzijian/project1_database/outcomes/v55/scenes/italian_flat/props")
parts = sorted(P.glob("glass_a_part*.obj"))
ms = [trimesh.load(str(f), process=True, force="mesh") for f in parts[:3]]
mesh = trimesh.util.concatenate(ms)
print("merged", len(mesh.vertices), len(mesh.faces))
pts = np.asarray(mesh.vertices[:50], float)
try:
    inside = mesh.contains(pts)
    print("contains OK:", inside[:8])
except Exception as e:
    print("contains RAISED", type(e).__name__, e)
try:
    m2 = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces, process=True)
    print("ray engine:", trimesh.ray.ray_triangle.__name__)
    inside2 = m2.contains(pts)
    print("contains2 OK:", inside2[:8])
except Exception as e:
    print("contains2 RAISED", type(e).__name__, e)
