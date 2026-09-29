# Stage-05 render chain: keyframes -> diagnostic preview -> final delivery
#
# Runs the three 09 render levels in order for the accepted stage-05 solve. Each mode writes into
# its own `frames_<mode>` directory, so nothing collides and nothing is overwritten. Every step is
# chained with `;` rather than `&&` on purpose: an earlier chain used `&&` and a non-zero exit from
# one step silently skipped the rest, which hid a failure instead of reporting it.
#
# 09's budget for this stage:
#   keyframes   960x540,  8-16 spp  -- camera and content screening
#   preview    1280x720, 16-32 spp  -- full duration, no skipped frames
#   final      1920x1080,     64 spp -- the delivery
#
# The vertical framing of this interaction is the binding constraint (the motion's vertical span is
# about three times its horizontal span), so `interaction` scope is the one used; the trigger's later
# fall to the floor leaves the bottom of frame and that is disclosed rather than hidden.

$ErrorActionPreference = 'Continue'
$blender = 'D:\workspace\project1_database\tools\runtime_local\blender-4.2.23-windows-x64\blender.exe'
$script  = 'D:\workspace\project1_database\tools\v55_render_05.py'
$run     = 'D:\workspace\project1_database\outcomes\v55\italian_flat\box_hits_bottle\20260929T110000'
$out     = "$run\render"

Write-Output "=== STAGE 05 RENDER CHAIN START $(Get-Date -Format o) ==="

Write-Output ""
Write-Output "--- 1/3 keyframes 960x540 16spp at release / pre-contact / strike / mid-topple / end ---"
& $blender --background --factory-startup --python $script -- --run $run --out $out `
    --mode keyframes --res 960x540 --spp 16 --threads 8 --framelist 0,5,8,9,12,20,40,61 2>&1 |
    Select-String -Pattern 'compliant camera|frame +[0-9]|rendered |redirected|persistent|threads|RENDER DONE|Traceback|FATAL|Error'
Write-Output "keyframes exit=$LASTEXITCODE"

Write-Output ""
Write-Output "--- 2/3 continuous preview 1280x720 16spp, all 62 frames, real time ---"
& $blender --background --factory-startup --python $script -- --run $run --out $out `
    --mode preview --res 1280x720 --spp 16 --threads 8 2>&1 |
    Select-String -Pattern 'frame +[0-9]|rendered |RENDER DONE|Traceback|FATAL|Error'
Write-Output "preview exit=$LASTEXITCODE"

Write-Output ""
Write-Output "--- 3/3 final cost probe: 3 frames at 1920x1080 64spp, as 09 section 3 requires ---"
& $blender --background --factory-startup --python $script -- --run $run --out $out `
    --mode finalprobe --res 1920x1080 --spp 64 --threads 8 --framelist 0,9,61 2>&1 |
    Select-String -Pattern 'frame +[0-9]|rendered |RENDER DONE|Traceback|FATAL|Error'
Write-Output "finalprobe exit=$LASTEXITCODE"

Write-Output ""
Write-Output "=== STAGE 05 RENDER CHAIN END $(Get-Date -Format o) ==="
