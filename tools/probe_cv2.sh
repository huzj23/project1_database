#!/usr/bin/env bash
# Is OpenCV's image encoding functional in this environment?
source /data/raw/huzijian/project1_database/tools/server_env.sh
PY="$WS/tools/conda_env/bin/python"
OUT="$WS/tmp/cvtest"
mkdir -p "$OUT"

"$PY" -X faulthandler - <<PY 2>&1 | grep -E '^CV|^Fatal|File "' 
import os, numpy as np, cv2
def p(*a): print("CV", *a, flush=True)
out = "$OUT"
p("cv2", cv2.__version__, "build info has PNG:", "PNG" in cv2.getBuildInformation())

u8 = (np.random.rand(32, 48, 3) * 255).astype(np.uint8)
p("imwrite jpg u8  :", cv2.imwrite(os.path.join(out, "a.jpg"), u8))
p("imwrite png u8  :", cv2.imwrite(os.path.join(out, "b.png"), u8))

u16 = (np.random.rand(32, 48) * 4000).astype(np.uint16)
p("imwrite png u16 :", cv2.imwrite(os.path.join(out, "c.png"), u16))
p("imwrite png u16 contig:", cv2.imwrite(os.path.join(out, "d.png"),
                                          np.ascontiguousarray(u16)))

u32 = (np.random.rand(32, 48, 1) * 3).astype(np.uint32)
p("imwrite png u32 :", cv2.imwrite(os.path.join(out, "e.png"), u32))

p("files:", sorted(os.listdir(out)))
for f in sorted(os.listdir(out)):
    p("  size", f, os.path.getsize(os.path.join(out, f)))
p("cv2 test done")
PY
