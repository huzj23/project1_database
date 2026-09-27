import numpy as np, os, json
from PIL import Image

R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
D = f"{R}/datasets/turntable_carry/seed-005001/x1"

seg = np.array(Image.open(f"{D}/segmentation/segmentation_00000.png"))
print("seg shape:", seg.shape, "dtype:", seg.dtype)
vals, counts = np.unique(seg, return_counts=True)
print("unique values / counts:")
for v, c in zip(vals, counts):
    print(f"   {v}: {c}")

for v, c in zip(vals, counts):
    m = seg == v
    if c < 200 or c > 0.4 * seg.size:
        continue
    ys, xs = np.nonzero(m)
    print(f"--- value {v}: n={c} bbox x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}] "
          f"w={xs.max()-xs.min()+1} h={ys.max()-ys.min()+1} "
          f"cx={xs.mean():.1f} cy={ys.mean():.1f}")

# save the mask for value 2
m2 = (seg == 2).astype(np.uint8) * 255
Image.fromarray(m2).save("/data/raw/huzijian/project1_database/tmp/zz_mask2.png")
print("saved mask for value 2")
