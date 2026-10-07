# tools/v65 — V6.5 six-hour final-video pipeline

Authoritative revision of each script. Superseded revisions are kept, not deleted, because each one records a
defect that was found and fixed; the defect notes live in the file headers and in §8 of the final report.

| purpose | authoritative file | superseded |
|---|---|---|
| solve one world at 1920 Hz, write trajectory/events/contacts | `solve_main_r2.py` | `tools/v65/solve_main.py` |
| gate 2 geometry / penetration over the whole scene | `geometry_gate.py` | — |
| gate 2 detector self-test (can the gate fail?) | `geometry_selftest_r4.py` | `geometry_selftest.py`, `_r3` |
| diagnose why an earlier self-test mis-fired | `gselftest_diagnose.py` | — |
| gate 4 camera path from the real event table | `camera_design_r2.py` | `camera_design.py` |
| build the animated film scene from the solved trajectory | `build_film_scene_r6.py` | `build_film_scene.py`, `_r2`..`_r5` |
| render a disjoint frame block, resumable, GPU-readback | `render_range_r3.py` | `render_range.py`, `_r2` |
| launch one GPU-scoped render block | `launch_render_block_r3.py` | `launch_render_block.py`, `_r2` |
| launch the six-worker fleet | `launch_fleet.py` | `launch_group.py`, `spec_round1.json` |
| monitor the fleet and recompute the ETA | `monitor_fleet.py` | `read_eta.py` |
| per-frame QA, encode, container verification | `assemble_video.py` | — |
| run-manifest, layout/physics config, final report | `build_manifest_r2.py`, `emit_deliverables.py`, `write_final_report.py` | `build_manifest.py` |
| probes that read facts out of the files | `probe_source_scene.py`, `probe_fog_topology.py`, `probe_tape.py`, `probe_gaps.py`, `probe_tail_assets.py` | — |
| Blender wrapper (project-scoped scratch/loader) | `v65_blender.sh` | — |

## The three facts these probes established, which the pipeline depends on

1. **The `Fog` scene is composited by the main `Scene`.** The main scene's compositor contains a Render Layers node
   bound to scene `Fog`, so only `Scene` is rendered. `Fog` has **zero** compositor nodes; rendering it separately
   would both double the cost and overwrite the finished frame with a raw uncomposited layer.
2. **`yaw` in the layout is in RADIANS.** F44 records `2.356194490192345` = 135°, matching the placement report.
   Treating it as degrees yields impossible negative clearances.
3. **`Floor_main` is the name of EIGHT distinct bodies** (ids 22–29). Any code that selects a support surface by name
   picks a different slab from the one the chain stands on (F47 rests on id 26).

## Validation hooks that keep the numbers honest

* `emit_deliverables.py` recomputes F01→F02 face-to-face clearance and **refuses to publish** if it disagrees with the
  proven trunk spacing (0.04856 m) by more than 2 mm.
* `build_film_scene_r6.py` asserts that the common-mode shape check covered as many objects as the manifest lists, so
  it cannot pass vacuously.
* `render_range_r3.py` refuses to start without an authorised GPU UUID, refuses `CUDA_VISIBLE_DEVICES`, and inspects
  every co-tenant process's `/proc/<pid>/cmdline` to prove it belongs to this run.
