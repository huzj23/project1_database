# Stage 05 — reproduction commands

Every command below is absolute and was actually run. They are grouped by what they produce, in the
order they were run. Nothing here contains a credential: the SSH helper reads the password from
`log/key.txt` at call time and injects it only into the SSH child process.

Machine facts these commands assume:

| item | value |
| --- | --- |
| project root | `D:\workspace\project1_database` |
| local Blender | `D:\workspace\project1_database\tools\runtime_local\blender-4.2.23-windows-x64\blender.exe` (4.2.23 LTS) |
| local Python (control) | `C:\Users\12447\AppData\Local\Programs\Python\Python39\python.exe` |
| server | `gpu0001`, account `wangzile`, conda python `/data/raw/huzijian/project1_database/tools/conda_env/bin/python` |
| server project root | `/data/raw/huzijian/project1_database` |
| ffmpeg | `C:\Users\12447\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe` |
| accepted run | `outcomes\v55\italian_flat\box_hits_bottle\20260929T110000` |

`RUN` and `OUT` below stand for that accepted run directory and `<RUN>\render`.

---

## 1. Physics — solved on the server, CPU only

The solver never imports `bpy`; the server solves, the local Blender replays.

```powershell
# upload the current stage-05 solve script
& $py tools\v55_ssh.py put --local tools\v55_final_05.py `
    --remote /data/raw/huzijian/project1_database/tools/v55_final_05.py

# run it in the project's own tmux session, writing into the run directory
& $py tools\v55_ssh.py run --cmd "cd /data/raw/huzijian/project1_database && /data/raw/huzijian/project1_database/tools/conda_env/bin/python /data/raw/huzijian/project1_database/tools/v55_final_05.py 20260929T110000"
```

The control (no trigger) and the decisive experiment are separate scripts and were run the same way:
`v55_control_05.py` (identical layout with the trigger **absent**, per 04 §54) and
`v55_decisive_05.py` (correct-proxy sweep across target and offset).

## 2. Evidence sync — server to local

```powershell
& $py tools\v55_ssh.py getdir `
    --remote /data/raw/huzijian/project1_database/outcomes/v55/italian_flat/box_hits_bottle/20260929T110000 `
    --local  outcomes\v55\italian_flat\box_hits_bottle\20260929T110000
```

## 3. Camera — framing search, then occlusion, then choice

```powershell
# framing space: azimuth x elevation x distance x focal length, with 09's bands reported explicitly
& $py tools\v55_camera_opt_05.py

# 09's framing bands measured over the recorded trajectory, for several interval definitions
& $py tools\v55_framing_analysis.py
```

The render script then reads `camera_opt.json` and adds the occlusion test, which needs Blender:

```powershell
& $blender --background --factory-startup --python tools\v55_render_05.py -- `
    --run "$RUN" --out "$OUT" --mode probe
```

## 4. Render — three 09 levels, 8 threads, one heavy task

```powershell
# keyframes 960x540 16 spp at release / descent / contact / mid-topple / end
& $blender --background --factory-startup --python tools\v55_render_05.py -- `
    --run "$RUN" --out "$OUT" --mode keyframes --res 960x540 --spp 16 --threads 8 `
    --framelist 0,5,8,9,12,20,40,61

# continuous preview 1280x720 16 spp, all 62 frames, real time, no skipped frames
& $blender --background --factory-startup --python tools\v55_render_05.py -- `
    --run "$RUN" --out "$OUT" --mode preview --res 1280x720 --spp 16 --threads 8

# 09 section 3: time 3 frames at the delivery settings before committing to the full pass
& $blender --background --factory-startup --python tools\v55_render_05.py -- `
    --run "$RUN" --out "$OUT" --mode finalprobe --res 1920x1080 --spp 64 --threads 8 `
    --framelist 0,9,61

# the replayable project, with no rendering
& $blender --background --factory-startup --python tools\v55_render_05.py -- `
    --run "$RUN" --out "$OUT" --mode replay

# final delivery 1920x1080 64 spp
& $blender --background --factory-startup --python tools\v55_render_05.py -- `
    --run "$RUN" --out "$OUT" --mode final --res 1920x1080 --spp 64 --threads 8
```

`tools\v55_render_05_chain.ps1` runs the first three in order. `tools\v55_probe_render.py` is a
minimal one-frame render used to isolate a render hang; it is diagnostic only.

## 5. Verification

```powershell
# numeric verification of every delivered PNG: size, bit depth, blankness, inter-frame change
& $py tools\v55_check_png.py "$OUT\frames_keyframes\f_0000.png" "$OUT\frames_keyframes\f_0009.png"
& $py tools\v55_check_png.py --diff "$OUT\frames_keyframes\f_0000.png" "$OUT\frames_keyframes\f_0009.png"

# encode to H.264 and verify: ffprobe, full decode, sampled frames, and motion in the ENCODED file
& $py tools\v55_encode_05.py "$OUT\frames_final" "$RUN\video.mp4" 24 19 "$RUN"
```

## 6. Housekeeping — archive, never delete

```powershell
# move a tree into remove/ with a per-file SHA-256 manifest, then verify the hashes
& $py tools\v55_archive_runtime.py "outcomes\v55\italian_flat\box_hits_bottle\20260929T110000\render" `
    v55_stage05_render_prepersist
```

## 7. What each script is for

| script | purpose |
| --- | --- |
| `tools/v55_render_05.py` | build the replay animation from the recorded trajectory, choose the camera by measured visibility, render each 09 level, save `replay.blend` |
| `tools/v55_camera_opt_05.py` | search the framing space and report 09's bands, including the arithmetic proof that the 45–65% width band is unreachable for this event |
| `tools/v55_framing_analysis.py` | measure 09's bands over the recorded trajectory for several interval definitions |
| `tools/v55_encode_05.py` | encode H.264/yuv420p and verify it three ways plus a motion check from the encoded file |
| `tools/v55_check_png.py` | stdlib PNG reader (8- and 16-bit) with per-frame statistics and frame differencing |
| `tools/v55_archive_runtime.py` | move a tree to `remove/<label>_<utc>/` with a hash-verified manifest |
| `tools/v55_probe_render.py` | one-frame render, to separate a render fault from an animation fault |
| `tools/v55_ssh.py` | SSH/SFTP wrapper that injects the password into the child environment only, and refuses paths outside the project root |
| `tools/v55_blender_libdir.py` | test whether the server Blender starts with the project's own library directory (stage 01 recorded that it does) |
