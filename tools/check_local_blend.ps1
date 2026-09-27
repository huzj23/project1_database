# Verify the downloaded preview .blend opens on the LOCAL Blender 5.2.2 and
# that every texture is packed (so the user can just double-click it).
$ErrorActionPreference = 'Continue'
$bl = 'D:\workspace\project1_database\outcomes\_hf_preview\replicad_apartment-special_plush_elephant-preview.blend'
Write-Output "=== local Blender opens the preview .blend? ==="
Write-Output "  file: $bl  ($([math]::Round((Get-Item $bl).Length/1MB,2)) MB)"

$py = @'
import bpy, os, sys
print("CK blender :", bpy.app.version_string)
print("CK file    :", os.path.basename(bpy.data.filepath))
objs = [(o.name, o.type) for o in bpy.data.objects]
print("CK objects :", len(objs))
for n, t in objs: print(f"CK   {t:8s} {n}")
print("CK lights  :", len([o for o in bpy.data.objects if o.type=='LIGHT']))
print("CK colls   :", [c.name for c in bpy.data.collections])
print("CK worlds  :", [w.name for w in bpy.data.worlds])
print("CK scene world:", bpy.context.scene.world.name if bpy.context.scene.world else None)
unp = [i.name for i in bpy.data.images if i.filepath and not i.packed_file]
print("CK images  :", len(bpy.data.images), "unpacked:", len(unp))
print("CK materials:", len(bpy.data.materials))
# is the wood material actually on the disc?
for o in bpy.data.objects:
    if o.type == 'MESH' and o.data.materials:
        mats = [m.name for m in o.data.materials if m]
        if 'support_object' in o.name or 'wood' in ' '.join(mats).lower():
            print(f"CK {o.name}: mats={mats}")
# camera
for o in bpy.data.objects:
    if o.type == 'CAMERA':
        print("CK camera  :", o.name, tuple(round(v,4) for v in o.location))
print("CK OK")
'@
Set-Content -Path 'tmp\ck_blend.py' -Value $py -Encoding ascii
& 'D:\blender\blender.exe' --background --factory-startup $bl --python 'tmp\ck_blend.py' 2>&1 |
  Select-String -Pattern '^CK' | ForEach-Object { "  $($_.Line)" }