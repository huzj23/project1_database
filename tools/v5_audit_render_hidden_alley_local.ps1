$ErrorActionPreference = 'Stop'

$workspace = 'D:\workspace\project1_database'
$blender = 'D:\workspace\project1_database\tools\runtime_local\blender-4.2.23-windows-x64\blender.exe'
$source = 'D:\workspace\project1_database\models\backgrounds\candidates\hidden_alley\extracted\ph_hidden_alley.blend'
$auditScript = 'D:\workspace\project1_database\tools\v5_inspect_scene_file.py'
$renderScript = 'D:\workspace\project1_database\tools\v5_render_scene_still.py'
$audit = 'D:\workspace\project1_database\outcomes\v5_asset_review\scenes\audits\hidden_alley.json'
$output = 'D:\workspace\project1_database\outcomes\v5_asset_review\scenes\hidden_alley.png'
$report = 'D:\workspace\project1_database\outcomes\v5_asset_review\scenes\hidden_alley.json'

foreach ($path in @($blender, $source, $auditScript, $renderScript)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required project file is missing: $path"
    }
}

$previous = @{
    CUDA_VISIBLE_DEVICES = $env:CUDA_VISIBLE_DEVICES
    KUBRIC_USE_GPU = $env:KUBRIC_USE_GPU
    OMP_NUM_THREADS = $env:OMP_NUM_THREADS
    TEMP = $env:TEMP
    TMP = $env:TMP
}

try {
    $env:CUDA_VISIBLE_DEVICES = ''
    $env:KUBRIC_USE_GPU = 'false'
    $env:OMP_NUM_THREADS = '8'
    $env:TEMP = 'D:\workspace\project1_database\tmp'
    $env:TMP = 'D:\workspace\project1_database\tmp'

    & $blender --background $source --threads 8 --python $auditScript -- `
        --tag hidden_alley --report $audit --workspace $workspace
    if ($LASTEXITCODE -ne 0) {
        throw "Hidden Alley audit failed with exit code $LASTEXITCODE"
    }

    # The source compositor renders a second volumetric Fog scene and exceeded
    # 25 GiB private memory without producing a file.  For asset review, keep
    # the authored scene/camera/lights/materials but disable only compositing.
    & $blender --background $source --threads 8 --python $renderScript -- `
        --tag hidden_alley --output $output --report $report --camera hidden_alley_camera `
        --samples 16 --disable-compositing --workspace $workspace
    if ($LASTEXITCODE -ne 0) {
        throw "Hidden Alley render failed with exit code $LASTEXITCODE"
    }
}
finally {
    foreach ($name in $previous.Keys) {
        $value = $previous[$name]
        if ($null -eq $value) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item -LiteralPath "Env:$name" -Value $value
        }
    }
}
