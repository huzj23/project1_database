"""Extract the embedded legacy .basis texture from a ReplicaCAD GLB."""

import json
import struct
from pathlib import Path


SOURCE = Path(
    r"D:\blender\data_found_online\ReplicaCAD_BakedLighting_full\stages\Baked_sc0_staging_00.glb"
)
OUTPUT_DIR = Path(r"D:\workspace\project1_database\blender_previews\replica_texture_work")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with SOURCE.open("rb") as handle:
    magic, version, total_length = struct.unpack("<4sII", handle.read(12))
    if magic != b"glTF" or version != 2:
        raise RuntimeError("Not a glTF 2.0 binary")
    json_length, json_type = struct.unpack("<I4s", handle.read(8))
    document = json.loads(handle.read(json_length).decode("utf-8"))
    bin_length, bin_type = struct.unpack("<I4s", handle.read(8))
    binary = handle.read(bin_length)

image = document["images"][0]
view = document["bufferViews"][image["bufferView"]]
offset = int(view.get("byteOffset", 0))
length = int(view["byteLength"])
texture = binary[offset : offset + length]
output = OUTPUT_DIR / "Baked_sc0_Image_0.basis"
output.write_bytes(texture)
print("EXTRACTED_BASIS", output, "bytes", len(texture), "mime", image.get("mimeType"))
