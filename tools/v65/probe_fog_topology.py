"""How does the Fog layer actually reach the final frame?

An earlier revision of the probe tested `node.type == "RLAYER"`, but Blender's identifier for a compositor Render
Layers node is `"R_LAYERS"`. The condition therefore never matched, the `scene` key was never populated, and the
probe printed `scene=None` for every render-layer node -- from which the wrong conclusion ("the Fog scene is not
bound into the main compositor") was nearly drawn. That is the same silent-failure family this project keeps hitting,
so the node type identifiers are now taken from Blender itself and printed, rather than assumed.

What actually matters for the render: whether the main `Scene` pulls in the `Fog` scene through its compositor (in
which case rendering `Scene` alone composites the fog and the Fog scene must NOT be rendered separately), or whether
the fog arrives some other way. Rendering it twice would both double the cost and overwrite the composited pixels.
"""

from pathlib import Path
import json

import bpy

ROOT = Path("/data/raw/huzijian/project1_database")
SOURCE = ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"
OUT = ROOT / "outcomes/v65/radio_scurve_domino/v65_20261007_final"

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))

print("=== the identifiers Blender actually uses for these nodes ===", flush=True)
for t in ("CompositorNodeRLayers", "CompositorNodeComposite", "CompositorNodeOutputFile",
          "CompositorNodeImage", "CompositorNodeAlphaOver"):
    try:
        print(f"  {t} -> type={getattr(bpy.types, t).bl_rna.properties['type'].default!r}", flush=True)
    except Exception as exc:
        print(f"  {t} -> {exc}", flush=True)

report = {}
for s in bpy.data.scenes:
    rows = []
    if s.use_nodes and s.node_tree:
        for n in s.node_tree.nodes:
            row = {"name": n.name, "type": n.type, "bl_idname": n.bl_idname}
            if n.type == "R_LAYERS":
                # the real question: which scene does this render-layer node pull from?
                bound = getattr(n, "scene", None)
                row["bound_scene"] = bound.name if bound else None
                row["bound_scene_is_self"] = (bound is None or bound.name == s.name)
                row["layer_name"] = getattr(n, "layer", None)
            if n.type == "IMAGE":
                row["image"] = n.image.name if n.image else None
                row["image_filepath"] = (n.image.filepath if n.image else None)
            rows.append(row)
    report[s.name] = {"engine": s.render.engine, "nodes": rows,
                      "n_output_file_nodes": sum(1 for r in rows if r["type"] == "OUTPUT_FILE")}
    print(f"\n=== scene {s.name} (engine {s.render.engine}) ===", flush=True)
    for r in rows:
        extra = ""
        if r["type"] == "R_LAYERS":
            extra = f"  pull_from={r['bound_scene']}  is_self={r['bound_scene_is_self']}"
        if r["type"] == "IMAGE":
            extra = f"  image={r['image']}  file={r['image_filepath']}"
        print(f"  {r['name']:<26} {r['type']:<12} {r['bl_idname']}{extra}", flush=True)

main = report["Scene"]
pulling = [r for r in main["nodes"] if r["type"] == "R_LAYERS" and not r["bound_scene_is_self"]]
print(f"\n  main Scene render-layer nodes that pull from ANOTHER scene: "
      f"{[(r['name'], r['bound_scene']) for r in pulling] or 'NONE'}", flush=True)
print(f"  -> rendering 'Scene' alone {'DOES' if pulling else 'does NOT'} composite the other scene; "
      f"the Fog scene {'must not' if pulling else 'may need to'} be rendered separately", flush=True)

(OUT / "fog_topology.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("\nFOG_TOPOLOGY_DONE", flush=True)
