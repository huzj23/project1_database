"""What is inside the repaired tape blend, and what does the render pipeline need from it?

The V6.4 tape repair produced `models/derived/v64/common_assets_r2/tape_common_r9.blend` with its own atlas
`tape_own_atlas_r9.png`. The older `common_assets_r1` library still holds the pre-repair 48 `v63_asset_tape_*` wedges.
The film must use the repaired one (V6.4 plan section 1 and the V6.5 plan both say so), so this probe reports the
object names, vertex/triangle counts, per-object shape hashes, image dependencies and materials of the repaired blend,
which is what the scene builder needs in order to attach it to actor F22 correctly.
"""

import hashlib
import json
from pathlib import Path

import bpy
import numpy as np

ROOT = Path("/data/raw/huzijian/project1_database")
TAPE = ROOT / "models/derived/v64/common_assets_r2/tape_common_r9.blend"
OUT = ROOT / "outcomes/v65/radio_scurve_domino/v65_20261007_final"
OUT.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=str(TAPE))
rows = []
total_v = total_t = 0
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    o.data.calc_loop_triangles()
    v = np.array([list(x.co) for x in o.data.vertices], dtype="<f8")
    t = np.array([list(x.vertices) for x in o.data.loop_triangles], dtype="<i4")
    h = hashlib.sha256(v.tobytes() + t.tobytes()).hexdigest()
    total_v += len(v)
    total_t += len(t)
    rows.append({"name": o.name, "vertices": int(len(v)), "triangles": int(len(t)),
                 "shape_sha256": h,
                 "materials": [m.name for m in o.data.materials],
                 "uv_layers": [u.name for u in o.data.uv_layers],
                 "matrix_world": [list(r) for r in o.matrix_world]})

imgs = [{"name": i.name, "source": i.source, "filepath": i.filepath,
         "packed": bool(i.packed_file), "size": list(i.size)} for i in bpy.data.images]
mats = []
for m in bpy.data.materials:
    tex = []
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image:
                tex.append({"node": n.name, "image": n.image.name,
                            "interpolation": n.interpolation, "extension": n.extension})
    mats.append({"name": m.name, "images": tex})

report = {"tape_blend": str(TAPE), "objects": rows, "n_objects": len(rows),
          "total_vertices": total_v, "total_triangles": total_t,
          "images": imgs, "materials": mats,
          "blender": bpy.app.version_string}

# also report what the OLD library holds, so the difference is explicit and the wrong one cannot be picked silently
old = ROOT / "tmp/v63_node11/common_assets_r1/common_assets.blend"
report["old_library"] = str(old)
with bpy.data.libraries.load(str(old), link=False) as (src, dst):
    report["old_tape_objects"] = [n for n in src.objects if "tape" in n][:60]
    report["old_tape_count"] = len([n for n in src.objects if "tape" in n])

(OUT / "tape_probe.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"TAPE objects={len(rows)} verts={total_v} tris={total_t}", flush=True)
for r in rows[:6]:
    print(f"  {r['name']:<28} v={r['vertices']:<5} t={r['triangles']:<5} "
          f"mat={r['materials']} uv={r['uv_layers']}", flush=True)
print(f"images: {imgs}", flush=True)
print(f"old library tape objects: {report['old_tape_count']}", flush=True)
print("TAPE_PROBE_DONE", flush=True)
