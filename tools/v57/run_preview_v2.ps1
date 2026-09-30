# V5.7 preview render, corrected: per-pair pitch matching the solver.
#
# Runs in the background and is RESUMABLE: each candidate is written to its own PNG and the JSON report is
# flushed before each render, so an interruption never loses the measurements and a restart only re-renders
# what is missing.
#
# NOTE: ErrorActionPreference is NOT 'Stop'. Blender emits a harmless TBBmalloc notice on stderr, and with
# 'Stop' that notice aborts the job before any frame is produced.
$ErrorActionPreference = 'Continue'

$ws  = 'D:\workspace\project1_database'
$bl  = "$ws\tools\runtime_local\blender-4.2.23-windows-x64\blender.exe"
$src = "$ws\models\backgrounds\candidates\hidden_alley\extracted\ph_hidden_alley.blend"
$out = "$ws\outcomes\v57\domino_arc\preview_v2"
$log = "$ws\tmp\v57\preview_v2.log"

$env:CUDA_VISIBLE_DEVICES = ''
$env:KUBRIC_USE_GPU = 'false'
$env:OMP_NUM_THREADS = '8'
$env:PYTHONUNBUFFERED = '1'

New-Item -ItemType Directory -Force -Path $out | Out-Null

# C1 and C3 keep their framing from the first pass (both measured CLEAR with a well-exposed frame); C2 is
# added back because it has the largest measured arc deviation. `gap_frac 0.25` is the solver's value, so
# this preview shows the chain the solver will actually simulate.
& $bl --background --factory-startup -noaudio --python "$ws\tools\v57\preview_arc.py" -- `
    --blend $src --out $out --n 9 --cams C1,C2,C3 --res 1280x720 --spp 16 `
    --arc_r 2.0 --gap_frac 0.25 2>&1 | Tee-Object -FilePath $log -Append

Write-Output "preview_v2 finished, exit $LASTEXITCODE"
