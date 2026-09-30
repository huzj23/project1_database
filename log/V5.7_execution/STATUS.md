# V5.7 execution status — video B (domino arc)

Run: `outcomes/v57/domino_arc/arc03/` (the approved site; `arc01`/`arc02` are the rejected-site records)
Round contract: `log/V5.7_多米诺返工_1小时看图_10小时交付_20260930.md`
Last updated: 2026-09-30 09:05 (+08:00)

## Verdicts (kept separate, per the plan)

| verdict | state |
|---|---|
| `physics_passed` | **yes** — 9/9 toppled and fell, `all_fallen_and_still_down true`, motion-onset order exactly `[0,1,2,3,4,5,6,7,8]` at both 2° and 10°, min adjacent gap 2.0 / 1.4 frames, `bypass_violations []`, `all_have_contact true` |
| `render_verified` | **yes** — all numeric checks pass; see below |
| `executor_visual_reviewed` | **no — the model has no image input.** Never claimed. |
| `user_visual_accepted` | **preview yes; the final cut is still the user's call** |

## Gates

- **01:30 image gate**: missed by ~55 min. Cause: the site and camera had to be reworked, and the
  penetration gate had to be built before any render could be trusted.
- **10:30 playable MP4**: **met.** `video.mp4` exists and is decode-verified (see below).
- **14:00 overall**: met for video B. Delivery package complete.

## Delivered

`outcomes/v57/domino_arc/arc03/` — **64 frames, 24 fps, 2.67 s, 1280×720, h264/yuv420p, 0.81 MB.**

| artifact | what it is |
|---|---|
| `video.mp4` | the clip |
| `replay.blend` | reproducible project; animation keyed on all 10 bodies over frames 1..144 |
| `README.md` | one-page summary, timeline, site-move rationale, honest limitations |
| `APPROVAL.md` | what was approved, what was superseded, what is NOT approved |
| `review/` | the approved C3/C1 previews **and** real renders from the final site |
| `clearance_replay.json` | penetration on the **final animated project**, all 144 frames |
| `clearance_full.json`, `arc_result.json`, `trajectory.json` | physics and trajectory records |
| `scene_roles.json` | scene geometry classified by role (§3.2), from measurements |
| `video_verification.json`, `render_timings_all.json`, `hashes.json` | decode check, timings, source/config hashes |
| `camera.json`, `binding.json`, `render_config.json`, `preview_build.json` | actual camera and layout config |

## What is done

1. **Physics solve is correct and sequential.** `tools/v57/arc_solve.py` on `tools/v57/site_arc03.json`
   with `--pitch-m 0.155` (the approved uniform spacing) and a real-box trigger:
   `boxes_toppled 9/9`, `boxes_fallen 9/9`, `all_fallen_and_still_down true`, motion-onset order exactly
   `[0,1,2,3,4,5,6,7,8]` at 2° and 10°, every adjacent gap ≥ 2.0 / 1.4 frames, `bypass_violations []`.
2. **The trigger follows the chain's own tangent.** `make_trigger` in `tools/v56/b2_chain.py` was
   generalised from a hardcoded world `-X` offset and world `+Y` spin axis to the arc's own direction, and
   is verified to reduce *exactly* to the previously verified straight-chain expression at yaw 0 — the same
   linear and angular velocity to 9 decimal places. It is also **shorter** than box 0 and strikes at 94.5%
   of box 0's height, so it cannot pass over the first box.
3. **The spacing is the approved one.** Uniform centre pitch 0.155 m, chain length 1.2400 m, turn 35.52°.
   The user explicitly declined the per-pair tightening ("如无必要，可不修正"), so it was left alone.
4. **The penetration gate found a real defect, and it was fixed by moving the chain, not the scene.**
   `tools/v57/gate_penetration.py` tests every animated body at every frame against the whole scene, not
   just against the other boxes — the check whose absence let 12 of 13 boxes sit up to 37 mm inside an
   authored face in the previous round. On the **user-approved** site `(-1.20, +12.20)` it found boxes
   **2, 3, 6, 7 and 8 overlapping `stones`**, up to 304 overlapping triangle pairs, while all nine boxes
   correctly stood on `Floor_main`. `stones` and `leaves` are original authored geometry, so the **chain
   moved 1.0 m** to `(-1.10, +11.20)`, chord +36° — the closest fully clear site — rather than the scene
   being edited, hidden or deleted.
5. **The site scan now cannot lie the way it did.** `tools/v57/scan_sites.py` initially reported the
   approved site as clear. Three separate defects were found and fixed, and the tool now **validates itself**
   against the independently measured overlap pattern before it is allowed to scan:
   - it tested only the floor under each box *centre*, so a stone beside the centre passed;
   - it guessed the asset's local frame and divided out a yaw, but `import_asset_object` permutes and scales
     axes, so the guessed box was rotated 90° from the real one;
   - it read `BVHTree.overlap`'s `(index_in_self, index_in_other)` pair backwards, so it compared the probe
     with itself and called every site clear.
   It now imports through the same function the build uses and asks Blender's own `BVHTree.overlap` whether
   world-space triangles actually intersect. Its validation reproduces the ground truth exactly — expected
   boxes `[2,3,6,7,8]`, measured `[2,3,6,7,8]` — and it **refuses to scan** if it ever stops doing so.
6. **The V5.7 §1 check was performed on the final project.** The plan warns that the old
   "1014 pair-tests, zero interpenetration" result came from `_scene_with_boxes.blend`, a *pre-animation
   staging scene*, and is therefore not evidence about the footage. `clearance_replay.json` is run on
   **`replay.blend` with the animation in place**, over **all 144 frames**: **zero overlapping triangle
   pairs, 10/10 bodies on `Floor_main`**. Confirmed twice — once with the blend's own keyframes and once
   with the trajectory supplied.
7. **The cut was corrected for a real defect.** Measured propagation is **1.96 s**, so at the originally
   planned 120 frames, frames 48..119 — 72 frames, **3.00 s, 60% of the runtime** — would have been a
   completely static final state. The user chose the 64-frame cut (0.4 s establish + 1.96 s propagation +
   0.3 s final state), reusing all 60 already-rendered frames. The final state is still fully shown.
8. **The MP4 is decode-verified end to end.** `nb_frames 64`, `r_frame_rate 24/1`, duration 2.666667 s,
   timeline span 2.6250 s = exactly 63/24, frame interval 0.041666..0.041667 s, full decode clean, 5 stills
   extracted and hashed. `NUMERIC CHECKS: PASS`.

## Interruptions, recorded rather than smoothed over

- **A session reconnect killed the render at 05:49**, losing about 2 h. The 48 committed frames survived
  intact. The render was restarted with `Start-Process` so it is detached from the session lifecycle, and
  chunks were reduced from 24 to 12 frames to bound any repeat loss.
- **The encode stage initially failed** with "ffmpeg not found" after all 64 frames had been rendered: the
  expected path `...\Microsoft\Win32\...` does not exist on this machine — winget installs to
  `...\WinGet\Packages\...`. `verify_video.py`'s locator was fixed to search PATH and the winget tree.
- Both are recorded in `render_timings_all.json`.

## Remaining, not on the critical path

- **The final cut has not been visually reviewed by the model** (no image input). The frames are verified
  numerically and the look was approved before rendering, but the visual verdict is the user's.
- **The new background has not been separately signed off** as the old one was. The real renders in
  `review/` exist for exactly that judgement. The chain's framing is unchanged (same span 0.678, same 40 mm
  lens, 9/9 centres in frame) because the camera tracks the chain; only what is behind the boxes differs.
- **Git**: commit only this round's code, config and small records; keep others' changes; never force-push;
  never commit credentials, large models, `.blend` files or the video.

## Video A

Recorded as **blocked**, not as physically unreachable, with evidence in
`log/V5.6_execution/A_impossible.md` and `log/V5.6_execution/A_failure_for_review.md` (both present).
