import json, os
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
D = f"{R}/datasets/turntable_carry/seed-005001/x1"
for name in ["metadata.json", "trajectory.json", "support_trajectory.json"]:
    p = os.path.join(D, name)
    print("=" * 30, name, "exists:", os.path.exists(p))
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    print("  type:", type(d).__name__)
    if isinstance(d, dict):
        for k, v in list(d.items())[:20]:
            s = json.dumps(v)
            print(f"  {k}: {s[:220]}")
    else:
        print("  len:", len(d), "first:", json.dumps(d[0])[:400])
print("=" * 30, "rgb/segmentation/depth listing")
for sub in ["rgb", "segmentation", "depth"]:
    p = os.path.join(D, sub)
    fs = sorted(os.listdir(p))[:3]
    print(f"  {sub}: {fs}")
