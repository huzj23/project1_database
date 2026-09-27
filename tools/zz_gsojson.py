import json, sys

p = r"D:\blender\data_found_online\GSO_Kubric_PhysicsReady_full\GSO.json"
d = json.load(open(p))
print("top keys:", list(d)[:6])
print("name:", d.get("name"), "version:", d.get("version"))
print("data_dir:", d.get("data_dir"))
assets = d["assets"]
print("n assets:", len(assets))
e = assets.get("Sootheze_Cold_Therapy_Elephant")
print("elephant entry:", json.dumps(e, indent=1)[:1200])
# Show a couple of other entries to see the schema / any orientation hints
for k in list(assets)[:2]:
    print("---", k, json.dumps(assets[k], indent=1)[:600])
