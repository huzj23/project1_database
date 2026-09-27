import json
R = "/data/raw/huzijian/project1_database/code/physics-video-sim/physics-video-sim-main"
D = f"{R}/datasets/turntable_carry/seed-005001/x1"
d = json.load(open(f"{D}/metadata.json"))
print("=== render block ===")
print(json.dumps(d["render"], indent=1))
print("=== physics block ===")
print(json.dumps(d["physics"], indent=1))
print("=== validation block ===")
print(json.dumps(d["validation"], indent=1))
