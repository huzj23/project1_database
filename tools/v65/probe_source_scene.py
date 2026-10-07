"""V6.5 probe -- what is in the author's scene that the render pipeline must preserve and drive?

Answers, from the file itself rather than from earlier notes:
  * the scene list and, for each, its engine / world / view transform / compositor nodes;
  * whether a Fog scene exists and how it is composed with the main Scene;
  * the frame range and fps currently set;
  * the light objects (count, type, energy) so a later check can prove none were added or altered;
  * the objects that look like the radio (boombox) that the physics replaces;
  * the compositor wiring of the main Scene, so the new frames feed the SAME node graph.
"""

import json
from pathlib import Path

import bpy

ROOT = Path("/data/raw/huzijian/project1_database")
OUT = ROOT / "outcomes/v65/radio_scurve_domino/v65_20261007_final"
OUT.mkdir(parents=True, exist_ok=True)

SOURCE = ROOT / "models/backgrounds/candidates/hidden_alley/extracted/ph_hidden_alley.blend"
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))

report = {"source": str(SOURCE), "blender": bpy.app.version_string, "scenes": {}, "lights": {},
          "radio_like": [], "collections": [c.name for c in bpy.data.collections],
          "objects_total": len(bpy.data.objects), "images_total": len(bpy.data.images)}

for s in bpy.data.scenes:
    nodes = []
    if s.use_nodes and s.node_tree:
        for n in s.node_tree.nodes:
            row = {"name": n.name, "type": n.type, "bl_idname": n.bl_idname}
            if n.type == "OUTPUT_FILE":
                row["base_path"] = n.base_path
                row["file_slots"] = [{"path": sl.path, "name": sl.name} for sl in getattr(n, "layer_slots", [])]
            if n.type == "RLAYER":
                row["scene"] = getattr(n, "scene", None).name if getattr(n, "scene", None) else None
            nodes.append(row)
    report["scenes"][s.name] = {
        "engine": s.render.engine,
        "world": s.world.name if s.world else None,
        "view_transform": s.view_settings.view_transform,
        "exposure": s.view_settings.exposure,
        "gamma": s.view_settings.gamma,
        "look": s.view_settings.look,
        "resolution": [s.render.resolution_x, s.render.resolution_y, s.render.resolution_percentage],
        "fps": s.render.fps,
        "frame_start": s.frame_start, "frame_end": s.frame_end, "frame_current": s.frame_current,
        "use_nodes": s.use_nodes,
        "nodes": nodes,
        "cycles_samples": getattr(s.cycles, "samples", None) if hasattr(s, "cycles") else None,
        "cycles_device": getattr(s.cycles, "device", None) if hasattr(s, "cycles") else None,
        "eevee_taa": getattr(s.eevee, "taa_render_samples", None) if hasattr(s, "eevee") else None,
        "camera": s.camera.name if s.camera else None,
    }

for o in bpy.data.objects:
    if o.type == "LIGHT":
        report["lights"][o.name] = {"type": o.data.type, "energy": o.data.energy,
                                    "color": list(o.data.color)}
    nm = o.name.lower()
    if "boombox" in nm or "radio" in nm or "stereo" in nm:
        report["radio_like"].append({"name": o.name, "type": o.type,
                                     "matrix": [list(r) for r in o.matrix_world]})

# objects whose names or collections hint at the vegetation/ground the physics reproduces
report["possible_scenery"] = sorted({o.name.split(".")[0] for o in bpy.data.objects
                                     if o.type == "MESH"})[:80]

(OUT / "source_scene_probe.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("=== SCENES ===", flush=True)
for name, row in report["scenes"].items():
    print(f"  {name}: engine={row['engine']} world={row['world']} vt={row['view_transform']} "
          f"res={row['resolution']} fps={row['fps']} frames={row['frame_start']}..{row['frame_end']} "
          f"nodes={len(row['nodes'])} cam={row['camera']}", flush=True)
print(f"=== LIGHTS ({len(report['lights'])}) ===", flush=True)
for n, row in report["lights"].items():
    print(f"  {n}: {row['type']} energy={row['energy']}", flush=True)
print(f"=== RADIO-LIKE === {report['radio_like']}", flush=True)
print(f"=== main Scene compositor node types ===", flush=True)
for n in report["scenes"].get("Scene", {}).get("nodes", []):
    print(f"  {n['name']:<28} {n['type']:<14} {n['bl_idname']}", flush=True)
print("PROBE_DONE", flush=True)
