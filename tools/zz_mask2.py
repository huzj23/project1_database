import numpy as np, os
from PIL import Image
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
D = f"{R}/datasets/turntable_carry/seed-005001/x1"
for f in [0, 10, 20, 40, 60, 80]:
    p = f"{D}/segmentation/segmentation_{f:05d}.png"
    seg = np.array(Image.open(p))
    vals, counts = np.unique(seg, return_counts=True)
    desc = []
    for v, c in zip(vals, counts):
        if v == 0:
            continue
        m = seg == v
        ys, xs = np.nonzero(m)
        desc.append(f"v{v}:n={c} x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}] "
                    f"w={xs.max()-xs.min()+1} h={ys.max()-ys.min()+1}")
    print(f"frame {f:3d}: " + " | ".join(desc))
