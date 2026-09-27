import json
import struct
from pathlib import Path


path = Path(r"D:\blender\data_found_online\ReplicaCAD_BakedLighting_full\stages\Baked_sc0_staging_00.glb")
with path.open("rb") as handle:
    magic, version, total_length = struct.unpack("<4sII", handle.read(12))
    chunk_length, chunk_type = struct.unpack("<I4s", handle.read(8))
    document = json.loads(handle.read(chunk_length).decode("utf-8"))

print("GLB", magic, version, total_length)
print("IMAGES", json.dumps(document.get("images", []), indent=2))
print("TEXTURES", json.dumps(document.get("textures", []), indent=2))
print("MATERIALS", json.dumps(document.get("materials", []), indent=2)[:10000])
print("EXTENSIONS_USED", document.get("extensionsUsed"))
