import os, unicodedata
LOG = "/data/raw/huzijian/project1_database/log"
want = "V4.1_调研结果文档_碰撞体生成脚本对OBJ输入的坐标系缺陷_20260923.md"
print("expected repr:", repr(want))
print("expected utf8 bytes:", want.encode("utf-8").hex())
print()
for n in sorted(os.listdir(LOG)):
    if "V4.1" in n:
        print("found name repr:", repr(n))
        print("found  utf8 bytes:", n.encode("utf-8").hex())
        print("MATCHES EXPECTED:", n == want)
        p = os.path.join(LOG, n)
        print("size:", os.path.getsize(p))
        head = open(p, encoding="utf-8").readline().rstrip()
        print("first line:", head)
        print("decodes as utf-8: OK")
print()
print("all V4.1 entries:", [n for n in os.listdir(LOG) if "V4.1" in n])
