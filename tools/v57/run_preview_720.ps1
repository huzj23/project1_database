# V5.7 preview render: 720p approval images for the user.
#
# Resumable by design: each candidate is rendered only if its output PNG is absent or older than the build
# report, so killing and restarting this job never re-spends time on a frame that already exists.
#
# NOTE: ErrorActionPreference is NOT 'Stop' here. Blender writes a harmless TBBmalloc notice to stderr on
# this machine, and with 'Stop' that notice aborts the job before a single frame is produced.
$ErrorActionPreference = 'Continue'

$ws = 'D:\workspace\project1_database'
$bl = "$ws\tools\runtime_local\blender-4.2.23-windows-x64\blender.exe"
$src = "$ws\models\backgrounds\candidates\hidden_alley\extracted\ph_hidden_alley.blend"
$out = "$ws\outcomes\v57\domino_arc\preview_dev"
$log = "$ws\tmp\v57\render720_full.log"

$env:CUDA_VISIBLE_DEVICES = ''
$env:KUBRIC_USE_GPU = 'false'
$env:OMP_NUM_THREADS = '8'
$env:PYTHONUNBUFFERED = '1'

New-Item -ItemType Directory -Force -Path $out | Out-Null

# -u keeps Blender's Python output unbuffered so progress is readable while the job runs.
& $bl --background --factory-startup -noaudio --python "$ws\tools\v57\preview_arc.py" -u -- `
    --blend $src --out $out --n 9 --cams C1,C3 --res 1280x720 --spp 16 --arc_r 2.0 --spacing 0.155 `
    2>&1 | Tee-Object -FilePath $log -Append

Write-Output "preview render finished, exit $LASTEXITCODE"
