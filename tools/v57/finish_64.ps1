# V5.7 final delivery: fill the last 4 frames of the 64-frame cut, encode the MP4, verify the decode.
#
# WHY 64 FRAMES AND NOT 120
# -------------------------
# The measured physics is fully settled by frame 47 (1.96 s). At 120 frames (5.0 s) frames 48..119 -- 72
# frames, exactly 3.00 s -- show a completely static final state, which is 60% of the runtime with no
# information in it. The plan's own shape is "0.4 s establish + propagation + 0.7 s final state", which
# implies a 3.9 s propagation; the real propagation is 1.96 s. The 64-frame cut is
# 0.4 s establish + 1.96 s propagation + 0.3 s final state = 2.67 s, every frame carries information, and
# all 60 already-rendered frames are reused.
#
# NOTE: this file is deliberately pure ASCII. Windows PowerShell 5.1 reads .ps1 as ANSI, so non-ASCII
# characters in the script body caused a ParserError and the whole run failed before doing anything.
$ErrorActionPreference = 'Continue'
$ws  = 'D:\workspace\project1_database'
$bl  = "$ws\tools\runtime_local\blender-4.2.23-windows-x64\blender.exe"
$py  = 'C:\Users\12447\AppData\Local\Programs\Python\Python39\python.exe'
$Run = 'arc03'
$Frames = 64
$run = "$ws\outcomes\v57\domino_arc\$Run"
$log = "$run\logs"
$env:CUDA_VISIBLE_DEVICES = ''
$env:KUBRIC_USE_GPU = 'false'

function Stage($m) { Write-Output ""; Write-Output "=== [$([DateTime]::Now.ToString('HH:mm:ss'))] $m ===" }

Stage "fill frames up to $Frames"
$final = "$run\render"
$done = @(Get-ChildItem $final -Filter 'f_*.png' -EA SilentlyContinue | ForEach-Object { [int]($_.BaseName -replace 'f_','') })
$todo = @(0..($Frames-1) | Where-Object { $done -notcontains $_ })
Write-Output "  have $($done.Count) frames, missing $($todo.Count): $($todo -join ',')"

$attempt = 0
while ($todo.Count -gt 0 -and $attempt -lt 8) {
    $attempt++
    $tag = "fill_{0:d2}" -f $attempt
    $crun = "$run\_$tag"
    Remove-Item $crun -Recurse -Force -EA SilentlyContinue
    New-Item -ItemType Directory -Force -Path $crun | Out-Null
    $list = ($todo -join ',')
    Write-Output "  [$([DateTime]::Now.ToString('HH:mm:ss'))] $tag : $($todo.Count) frames ($list)"
    & $bl --background --factory-startup -noaudio --python "$ws\tools\v56\render.py" -- `
        --config "$run\render_config.json" --run $crun --mode "$tag" --res 1280x720 --spp 16 `
        --threads 8 --framelist $list 2>&1 | Tee-Object -FilePath "$log\fill_$tag.log" |
        Select-String -Pattern 'frame +\d+\s+\d|rendered \d+ frames|FATAL|Error'
    $produced = @(Get-ChildItem "$crun\render\frames_$tag" -Filter 'f_*.png' -EA SilentlyContinue)
    foreach ($f in $produced) { Move-Item $f.FullName (Join-Path $final $f.Name) -Force }
    Write-Output "    moved $($produced.Count) frames"
    $done = @(Get-ChildItem $final -Filter 'f_*.png' | ForEach-Object { [int]($_.BaseName -replace 'f_','') })
    $todo = @(0..($Frames-1) | Where-Object { $done -notcontains $_ })
}
$n = @(Get-ChildItem $final -Filter 'f_*.png' -EA SilentlyContinue).Count
Write-Output "  frames present: $n / $Frames"
if ($n -lt $Frames) { throw "not enough frames: $n / $Frames" }

Stage "archive frames beyond the $Frames-frame cut"
# The project never deletes: surplus frames move to remove\ with a record.
$extra = @(Get-ChildItem $final -Filter 'f_*.png' | Where-Object { [int]($_.BaseName -replace 'f_','') -ge $Frames })
if ($extra.Count -gt 0) {
    $rm = "$ws\remove\v57_arc03_frames_beyond_$Frames"
    New-Item -ItemType Directory -Force -Path $rm | Out-Null
    $rec = @()
    foreach ($f in $extra) {
        Move-Item $f.FullName (Join-Path $rm $f.Name) -Force
        $rec += $f.Name
    }
    @{moved_from=$final; moved_to=$rm; count=$rec.Count; files=$rec;
      reason="frames beyond the approved 64-frame cut; physics is fully settled by frame 47, so these are duplicate final-state stills"} |
      ConvertTo-Json | Set-Content "$rm\MOVED.json" -Encoding UTF8
    Write-Output "  archived $($rec.Count) frames to $rm"
} else { Write-Output "  nothing to archive" }
$n = @(Get-ChildItem $final -Filter 'f_*.png').Count
Write-Output "  cut length: $n frames"

Stage "encode MP4"
$ff = Get-ChildItem 'C:\Users\12447\AppData\Local\Microsoft\Win32\*\ffmpeg-8.1-full_build\bin\ffmpeg.exe' -EA SilentlyContinue | Select-Object -First 1
if (-not $ff) { $ff = Get-ChildItem 'C:\Users\12447\AppData\Local\Microsoft\Win32\*\*\ffmpeg*\bin\ffmpeg.exe' -EA SilentlyContinue | Select-Object -First 1 }
if (-not $ff) { throw "ffmpeg not found" }
Write-Output "  ffmpeg $($ff.FullName)"
& $ff.FullName -y -framerate 24 -start_number 0 -i "$final\f_%04d.png" `
    -c:v libx264 -pix_fmt yuv420p -crf 18 -preset slow "$run\video.mp4" `
    2>&1 | Tee-Object -FilePath "$log\encode_final.log" | Select-String -Pattern 'frame=|video:|error'
Get-Item "$run\video.mp4" | Select-Object Name,@{n='MB';e={[math]::Round($_.Length/1MB,2)}}

Stage "decode verification"
& $py "$ws\tools\v57\verify_video.py" --run $run --expect-frames $Frames --fps 24

Stage "camera.json"
if (-not (Test-Path "$run\camera.json")) {
    & $py -c "import json;c=json.load(open(r'$run\render_config.json',encoding='utf-8'))['camera'];json.dump(c,open(r'$run\camera.json','w',encoding='utf-8'),indent=2);print('camera.json written from render_config.json')"
}

Stage "source and config hashes"
& $py "$ws\tools\v57\make_hashes.py" --run $run --out "$run\hashes.json" | Select-Object -Last 3

Write-Output ""
Write-Output "=== DONE $([DateTime]::Now.ToString('HH:mm:ss')) ==="
Get-ChildItem $run -File | Sort-Object Name | Select-Object Name,@{n='MB';e={[math]::Round($_.Length/1MB,2)}} | Format-Table -AutoSize
