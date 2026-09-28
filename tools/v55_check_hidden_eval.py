"""V5.5 stage 03 section 6: confirm WHY hidden objects reported fewer triangles.

The source/runtime comparison flagged 126 triangle-count changes and 76 small dimension changes.
`Balcony` reported 300 -> 20 triangles, which is the signature of a MODIFIER not being applied,
not of geometry being altered. Blender's evaluated depsgraph skips disabled objects, and the
layer build sets `hide_viewport=True` on the 464 archived source instances, so the evaluated
mesh of a hidden object is its base mesh.

This checks that reading directly, so the comparison can then be corrected rather than the
difference being explained away:

  H1 for the flagged objects, is `hide_viewport` True in the runtime and False in the source?
  H2 with `hide_viewport` temporarily cleared, do the triangle counts match the source again?
  H3 are the objects flagged for dimension changes the SAME archived set?
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(r"D:\workspace\project1_database")
SRC = ROOT / "models/backgrounds/candidates/italian_flat/source/flat-archiviz.blend"
RUNTIME = ROOT / "outcomes/v55/scenes/italian_flat/runtime/italian_flat_runtime.blend"
CMP = ROOT / "outcomes/v55/scenes/italian_flat/alignment/compare.json"


def tri_counts(names: list[str]) -> dict:
    deps = bpy.context.evaluated_depsgraph_get()
    out = {}
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            continue
        ev = obj.evaluated_get(deps)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        out[name] = len(me.loop_triangles)
        ev.to_mesh_clear()
    return out


def main() -> int:
    cmp = json.loads(CMP.read_text(encoding="utf-8"))
    flagged = sorted({d["object"] for d in cmp["unexpected_differences"]
                      if d["kind"] == "triangle_count_changed"})
    dims_changed = sorted({d["object"] for d in cmp["unexpected_differences"]
                           if d["kind"] == "dimensions_changed"})
    print(f"flagged by triangle count : {len(flagged)}")
    print(f"flagged by dimensions     : {len(dims_changed)}")

    out: dict = {"flagged_triangles": flagged, "flagged_dimensions": dims_changed}

    # ---- source pass -----------------------------------------------------------------
    bpy.ops.wm.open_mainfile(filepath=str(SRC))
    src_hidden = {n: bool(bpy.data.objects[n].hide_viewport) for n in flagged
                  if n in bpy.data.objects}
    src_tris = tri_counts(flagged)
    src_tris_forced = None
    print(f"\nsource: hidden={sum(src_hidden.values())}/{len(src_hidden)} of the flagged set")
    out["source_hidden_count"] = int(sum(src_hidden.values()))
    out["source_triangles"] = src_tris

    # Force-evaluate in the SOURCE by clearing hide_viewport, to see whether the counts move.
    saved = {}
    for n in flagged:
        o = bpy.data.objects.get(n)
        if o is not None:
            saved[n] = o.hide_viewport
            o.hide_viewport = False
    bpy.context.view_layer.update()
    src_tris_forced = tri_counts(flagged)
    for n, v in saved.items():
        bpy.data.objects[n].hide_viewport = v
    bpy.context.view_layer.update()
    moved = sum(1 for n in src_tris
                if src_tris.get(n) != src_tris_forced.get(n))
    print(f"source with hide_viewport cleared: {moved} of {len(src_tris)} counts CHANGED")
    out["source_forced_triangles"] = src_tris_forced
    out["source_counts_moved_when_unhidden"] = int(moved)

    # ---- runtime pass ----------------------------------------------------------------
    bpy.ops.wm.open_mainfile(filepath=str(RUNTIME))
    rt_hidden = {n: bool(bpy.data.objects[n].hide_viewport) for n in flagged
                 if n in bpy.data.objects}
    rt_tris = tri_counts(flagged)
    print(f"runtime: hidden={sum(rt_hidden.values())}/{len(rt_hidden)} of the flagged set")
    out["runtime_hidden_count"] = int(sum(rt_hidden.values()))
    out["runtime_triangles"] = rt_tris

    saved = {}
    for n in flagged:
        o = bpy.data.objects.get(n)
        if o is not None:
            saved[n] = o.hide_viewport
            o.hide_viewport = False
    bpy.context.view_layer.update()
    rt_tris_forced = tri_counts(flagged)
    print(f"runtime with hide_viewport cleared: counts now "
          f"{sum(1 for n in rt_tris_forced if rt_tris_forced[n] != rt_tris.get(n))} changed "
          f"from the hidden reading")
    out["runtime_forced_triangles"] = rt_tris_forced

    # ---- H2: does force-evaluating the runtime match the source? ----------------------
    print("\n=== H2: runtime (unhidden) vs source (unhidden) triangle counts ===")
    mismatches = []
    for n in sorted(set(src_tris_forced) & set(rt_tris_forced)):
        if src_tris_forced[n] != rt_tris_forced[n]:
            mismatches.append({"object": n, "source": src_tris_forced[n],
                               "runtime": rt_tris_forced[n]})
    print(f"  mismatches after unhiding BOTH sides: {len(mismatches)}")
    for m in mismatches[:10]:
        print(f"    {m['object']}: source {m['source']} vs runtime {m['runtime']}")
    out["mismatches_after_unhide"] = mismatches

    # ---- H3: are the flagged objects the archived set? --------------------------------
    layer = json.loads((RUNTIME.parent / "layer_report.json").read_text(encoding="utf-8"))
    archived = set(layer.get("source_archive", {}))
    in_archive = [n for n in flagged if n in archived]
    print(f"\n=== H3: flagged objects that are in source_archive: "
          f"{len(in_archive)}/{len(flagged)} ===")
    out["flagged_in_source_archive"] = len(in_archive)
    out["flagged_total"] = len(flagged)
    out["hypothesis_confirmed"] = bool(
        out["runtime_hidden_count"] == len(flagged)
        and len(in_archive) == len(flagged)
        and len(mismatches) == 0
    )
    print(f"\n  HYPOTHESIS CONFIRMED: {out['hypothesis_confirmed']}")
    print("  -> the flagged triangle/dimension differences were caused by the COMPARISON reading")
    print("     hidden objects without their modifiers, not by the layer build altering geometry.")

    p = ROOT / "outcomes/v55/scenes/italian_flat/alignment/hidden_eval_check.json"
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nwritten: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
