# Stage 05 render: issue log

Running record of real defects found while producing the stage-05 delivery, kept separate from the
stage report so the report can stay readable. Each entry is a problem that was actually observed,
with the evidence and the resolution. Nothing here is a hypothetical.

---

## R1. The compositor was writing outside the project workspace

**Observed.** The first keyframe render printed `Saved: 'C:\tmp\0003.exr'`, and `C:\tmp` contained
`0001.exr`, `0003.exr`, `0009.exr` afterwards.

**Why it matters.** 09 section 1: "if the scene has external File Output nodes or cache paths,
redirect them to this run's workspace output first; do not save to the author's old paths." The
runtime copy carries the author's compositor, whose File Output node had `base_path = 'C:\tmp\'`.
Every rendered frame wrote a multi-megabyte EXR outside the project tree.

**Fixed.** The render script re-points every `OUTPUT_FILE` node at `<out>/compositor/` and records
the change in `compositor_redirect.json` with the old and new base paths, so the redirect is evidence
rather than a claim. Confirmed on the next run:
`redirected File Output node 'File Output': 'C:\tmp\' -> '...\20260929T110000\render\compositor'`.

---

## R2. 185 s/frame made a 62-frame clip impractical

**Observed.** Four keyframes took 305 s at 960x540/16 spp with persistence off, and the first
measurement was 185 s/frame  the frames were also never written, see R3.

**Fixed.** `scene.render.use_persistent_data = True`, which reuses the tessellated geometry, the BVH
and the shader state between frames. Measured effect: **185.5 s/frame -> 56.6 s/frame marginal**, a
3.3x reduction. The sampled image is the same computation, so this changes cost and not content, and
the per-frame times are recorded either way so the gain is measured rather than assumed.

---

## R3. The render wrote no file at all

**Observed.** A keyframe run reported `rendered 0 frames in 120.9 s` and the output directory held
only JSON.

**Cause.** `bpy.ops.render.render(write_still=True)` writes to `scene.render.filepath` and does not
reliably append a frame number to a path that has none. The script then looked for
`filepath + f"{f+1:04d}.png"`, a name that was never created.

**Fixed.** The output path is now set per frame to the exact destination file, and a missing file
raises immediately instead of being counted as a render.

---

## R4. Rendered frames were 16-bit, which the verifier could not read

**Observed.** `f_0000.png: bit depth 16 not handled` from `tools/v55_check_png.py`.

**Fixed.** The verifier handles 8- and 16-bit PNGs and collapses 16-bit samples for comparison, so
frames can be measured and diffed. Blender writes 16-bit PNGs by default; a checker that refused
them would have reported nothing about the actual delivery.

---

## R5. The frame directory was shared between render modes

**Observed.** Keyframe stills, the continuous preview and the final pass would all have written
`f_%04d.png` into one `frames/` directory. The script's own refuse-to-overwrite guard would then have
rejected the second pass, and mixing 960x540, 1280x720 and 1920x1080 frames in one folder would have
made the frame count meaningless.

**Fixed.** Each mode writes `frames_<mode>/`, so the guard protects each pass and no resolution is
mixed with another.

---

## R6. The camera search answered the wrong question

**Observed.** The first camera selection scored "does the motion fit the frame" and measured
19.3% target visibility and 12.7% trigger visibility from the camera it chose. Investigating that
produced two separate findings:

1. **The visibility metric was wrong.** It counted a ray that reached ANY sampled surface point, so a
   convex body could never exceed about 50%: the half facing away from every camera counted as
   occluded. That measures the object's shape, not the sightline. Replaced with the unoccluded
   fraction of the **camera-facing** surface, restricted to the frames where the body is actually on
   screen (the trigger's 43 post-strike frames falling to the floor were being counted as occluded
   even though the delivery never claims to show them). Corrected numbers: **target 100%, trigger
   78.5%** at the camera that was then chosen.

2. **Elevation was not searched.** The solve used one elevation from `camera.json`, so it could not
   find a low camera that avoided the room's furniture. With elevation in the search, the compliant
   camera is **azimuth 250 deg, elevation 0.0 deg**  09's preferred 0-8 degree band  with target
   91.4% and trigger 71.1% visible.

**Fixed.** `tools/v55_camera_opt_05.py` searches azimuth, elevation, distance and focal length and
emits a shortlist; the render script reads it in 09's own priority order (low elevation first, full
azimuth coverage) and stops as soon as a candidate satisfies every reachable 09 band and clears the
60% visibility rule. It also ranks elevation before visibility, because a 70-degree overhead camera
measured the best raw visibility (100%/80.4%) while being exactly the near-overhead shot 09 forbids.

**Note.** In RSS/summary terms this was one wrong measurement and one missing search dimension, both
caught by disbelieving a number that looked like a pass.

---

## R7. 09's 45-65% width band is unreachable for this event, and that is arithmetic

**Observed.** Catching an arithmetic error in my own first optimizer run: it reported the delivery
interval as 2482 mm vertical, because it included the trigger's post-strike fall to the room floor.
Correcting the interval to the actual causal event (release -> strike -> target topple) gives:

| quantity | value |
| --- | --- |
| framed region vertical extent | **897 mm** |
| framed region horizontal extent | **352 mm** |
| aspect ratio | **2.55:1 vertical** |
| triggered fall (descent alone) | 1241 mm |

**Why the band cannot be met.** A 16:9 frame is 0.5625:1, so for a vertical event
`span_y / span_x = 2.55 x 16/9 = 4.53`. A full-height span (`span_y = 1.0`) therefore yields
`span_x = 22.1%`. 09 asks for 45-65%, which would need `span_y = 204%`  more than the frame holds.
The full search over azimuth (every 10 deg), elevation (0-90 deg), distance (1.0-6.0 m) and focal
length (35/50/70 mm) found a maximum of **43.7%**, reachable only at an **80-degree near-overhead**
camera that 09 explicitly forbids, and the elevation sweep confirms the band is not reachable at any
elevation for this event.

**What was done.** Nothing was relaxed and no threshold was changed. The camera satisfies every other
09 band (safe frame MET, small-object height 11.3% MET at the chosen camera, visibility 91.4%/71.1%)
and the width shortfall is reported with its arithmetic cause in `camera_opt.json` and
`camera_solve.json`. The alternative  raising the drop or adding horizontal velocity to widen the
event  is forbidden by 05 section 2.6 (gravity only) and would be fabricating the physics anyway.

---

## R8. `acceptance.json` cites three evidence files that are not present

**Observed.** The stage-05 acceptance record lists

```
outcomes/v55/italian_flat/box_hits_bottle/energy_budget.json
outcomes/v55/italian_flat/box_hits_bottle/decisive_experiment.json
outcomes/v55/italian_flat/box_hits_bottle/final_search.json
```

and none of the three exists locally. They are written by `v55_final_05.py` (line 67, 68, 366, 376),
`v55_decisive_05.py` (line 301) and `v55_energy_budget.py` (line 244) into
`outcomes/v55/italian_flat/box_hits_bottle/` on the **server**, and the earlier evidence sync brought
across only the run directory `20260929T110000/`.

**Status: OPEN.** The SSH connection (both `run` and `put`) is timing out, so they cannot be fetched
at this moment. This is a delivery-completeness gap and not a physics one: the numbers those files
contain are summarised inside `acceptance.json` `unmet_requirements[0]`, which is where the bottle
substitution and the energy limit are documented. They must be synced before the stage is called
complete, and until they are, the stage report lists them as missing rather than implying the
evidence set is whole.

---

## R9. One deletion, of my own regenerable probe output

Recorded in full in `deletion_incident_05.md`. Three probe-mode JSONs were deleted with
`Remove-Item` instead of being moved to `remove/`. No source asset, solve record, trajectory or stage
report was affected. The archiver (`tools/v55_archive_runtime.py`) is used for every subsequent
cleanup, and two later archives were performed that way with hash verification.
