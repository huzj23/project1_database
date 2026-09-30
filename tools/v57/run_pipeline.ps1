# V5.7 domino arc -> final MP4, resumable at every stage.
#
# WHY A DRIVER RATHER THAN A SEQUENCE OF COMMANDS
# -----------------------------------------------
# The render is the expensive stage, so every earlier stage is guarded by a check of the artifact it
# produces, and the render itself is driven in resumable chunks. Re-running this script after any
# interruption continues from the first frame that is missing instead of redoing the whole run.
#
# Ordering matters and is enforced:
#   1. the physics must have toppled all nine boxes, or there is no video to render;
#   2. the authoritative clearance check must pass on the FULL trajectory, or the render would produce
#      footage of boxes clipping scenery -- which is the defect this round exists to fix;
#   3. only then does rendering start.
#
# `render.py` refuses to run when its output directory already holds frames, because the project never
# overwrites, so each chunk renders INTO A FRESH DIRECTORY and the finished frames are moved into the run's
# `render/` directory. That keeps the no-overwrite rule intact while still allowing a resumable render.
param(
    [string]$Run = 'arc03',
    [int]$Frames = 120,
    [int]$Chunk = 120,
    [int]$Spp = 16,
    [string]$Res = '1280x720'
)

$ErrorActionPreference = 'Continue'

$ws  = 'D:\workspace\project1_database'
$bl  = "$ws\tools\runtime_local\blender-4.2.23-windows-x64\blender.exe"
$py  = 'C:\Users\12447\AppData\Local\Programs\Python\Python39\python.exe'
$run = "$ws\outcomes\v57\domino_arc\$Run"
$log = "$run\logs"
$env:CUDA_VISIBLE_DEVICES = ''
$env:KUBRIC_USE_GPU = 'false'
$env:PYTHONUNBUFFERED = '1'

New-Item -ItemType Directory -Force -Path $log | Out-Null
# `render.py` creates <run>/render/frames_<mode>/ itself; the run's own `render` dir is where finished frames
# are collected, so it must exist before the first move.
New-Item -ItemType Directory -Force -Path "$run\render" | Out-Null

function Stage($m) { Write-Output ""; Write-Output "=== [$([DateTime]::Now.ToString('HH:mm:ss'))] $m ===" }

# ------------------------------------------------------------------ 1. physics verdict
Stage '1/4 physics verdict'
if (-not (Test-Path "$run\arc_result.json")) { throw "no arc_result.json in $run" }
$v = & $py -c @"
import json
s=json.load(open(r'$run\arc_result.json',encoding='utf-8'))['simulation']
print(s['boxes_toppled'], s['boxes_fallen'], s['all_toppled'], s.get('bypass_violations'),
      s.get('motion_onset_2deg_order'))
"@
Write-Output "  $v"
if ($v -notmatch '^9 9 True \[\] \[0, 1, 2, 3, 4, 5, 6, 7, 8\]$') {
    throw "physics gate failed: expected 9 toppled, 9 fallen, sequential order 0..8, no bypass"
}

# ------------------------------------------------------------------ 2. clearance on the full trajectory
Stage '2/4 authoritative clearance over the whole trajectory'
if (Test-Path "$run\clearance_full.json") {
    $c = & $py -c "import json;d=json.load(open(r'$run\clearance_full.json',encoding='utf-8'));print(d['passed'],d['frames_tested'],d['worst_overlap']['overlap_tris'],d['n_support_violations'])"
    Write-Output "  reusing existing: passed frames worst_overlaps support_violations = $c"
} else {
    & $bl --background --factory-startup -noaudio --python "$ws\tools\v57\clearance_check.py" -- `
        --blend "$run\staged.blend" --traj "$run\trajectory.json" --out "$run\clearance_full.json" `
        2>&1 | Tee-Object -FilePath "$log\2_clearance.log" | Select-String -Pattern 'testing|worst overlap|VERDICT'
    $c = & $py -c "import json;d=json.load(open(r'$run\clearance_full.json',encoding='utf-8'));print(d['passed'],d['frames_tested'],d['worst_overlap']['overlap_tris'],d['n_support_violations'])"
}
Write-Output "  passed frames worst_overlaps support_violations = $c"
if ($c -notmatch '^True ') { throw "clearance gate failed: $c" }

# ------------------------------------------------------------------ 3. render, in resumable chunks
Stage "3/4 render $Frames frames at $Res $Spp spp"
$final = "$run\render"
$done = @(Get-ChildItem $final -Filter 'f_*.png' -ErrorAction SilentlyContinue |
          ForEach-Object { [int]($_.BaseName -replace 'f_','') })
Write-Output "  frames already complete: $($done.Count) / $Frames"

$todo = @(0..($Frames - 1) | Where-Object { $done -notcontains $_ })
$attempt = 0
while ($todo.Count -gt 0 -and $attempt -lt 12) {
    $attempt++
    $batch = $todo | Select-Object -First $Chunk
    $tag = "chunk_{0:d2}" -f $attempt
    $crun = "$run\_$tag"
    Remove-Item $crun -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $crun | Out-Null
    $list = ($batch -join ',')
    Write-Output "  [$([DateTime]::Now.ToString('HH:mm:ss'))] $tag : $($batch.Count) frames ($($batch[0])..$($batch[-1]))"
    & $bl --background --factory-startup -noaudio --python "$ws\tools\v56\render.py" -- `
        --config "$run\render_config.json" --run $crun --mode "$tag" --res $Res --spp $Spp `
        --threads 8 --framelist $list `
        2>&1 | Tee-Object -FilePath "$log\3_render_$tag.log" | Select-String -Pattern 'frame +\d|rendered \d+ frames|FATAL|Error|Traceback'
    # Move whatever was produced into the run's render dir, then recompute what is missing. Doing it this
    # way means an interrupted chunk still contributes its finished frames.
    # `render.py` writes to `<run>/render/frames_<mode>/`, not to the run root, so the source path includes
    # the nested `render` directory. Getting this wrong would silently move nothing and the loop would
    # re-render the same chunk forever.
    $produced = @(Get-ChildItem "$crun\render\frames_$tag" -Filter 'f_*.png' -ErrorAction SilentlyContinue)
    foreach ($f in $produced) { Move-Item $f.FullName (Join-Path $final $f.Name) -Force }
    Write-Output "    moved $($produced.Count) frames; total now $((Get-ChildItem $final -Filter 'f_*.png').Count)"
    $done = @(Get-ChildItem $final -Filter 'f_*.png' | ForEach-Object { [int]($_.BaseName -replace 'f_','') })
    $todo = @(0..($Frames - 1) | Where-Object { $done -notcontains $_ })
}

$n = @(Get-ChildItem $final -Filter 'f_*.png' -ErrorAction SilentlyContinue).Count
Write-Output "  frames complete: $n / $Frames"
if ($n -lt $Frames) { throw "render incomplete: $n of $Frames frames" }

# ------------------------------------------------------------------ 4. encode and verify
Stage '4/4 encode MP4'
$ff = Get-ChildItem 'C:\Users\12447\AppData\Local\Microsoft\Win32\*\ffmpeg-8.1-full_build\bin\ffmpeg.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $ff) { $ff = Get-ChildItem 'C:\Users\12447\AppData\Local\Microsoft\Win32\*\*\ffmpeg*\bin\ffmpeg.exe' -ErrorAction SilentlyContinue | Select-Object -First 1 }
if (-not $ff) { throw "ffmpeg not found" }
& $ff.FullName -y -framerate 24 -start_number 0 -i "$final\f_%04d.png" `
    -c:v libx264 -pix_fmt yuv420p -crf 18 -preset slow "$run\video.mp4" `
    2>&1 | Tee-Object -FilePath "$log\4_encode.log" | Select-String -Pattern 'frame=|video:|error'
Write-Output "  wrote $run\video.mp4"
Get-Item "$run\video.mp4" | Select-Object Name, @{n='MB';e={[math]::Round($_.Length/1MB,2)}}

Write-Output ""
Write-Output "=== DONE $([DateTime]::Now.ToString('HH:mm:ss')) ==="
