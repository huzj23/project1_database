#!/usr/bin/env bash
# The script was uploaded from a Windows edit and picked up a UTF-8 BOM, which
# makes bash fail instantly with no output.  Strip it server-side and set the disc
# size there too, so the file never round-trips through PowerShell again.
export LC_ALL=C
source /data/raw/huzijian/project1_database/tools/server_env.sh
cd "$WS/tools" || exit 1
sed -i '1s/^\xEF\xBB\xBF//' turntable_wood.sh
sed -i 's/\r$//' turntable_wood.sh
sed -i 's/^DISC_R, DISC_T = .*/DISC_R, DISC_T = 0.30, 0.022/' turntable_wood.sh
echo "first bytes: $(head -c 20 turntable_wood.sh | od -c | head -2 | tr -s ' ')"
grep -n 'DISC_R, DISC_T' turntable_wood.sh
echo "--- running ---"
bash turntable_wood.sh > "$WS/log/tw.log" 2>&1
echo "exit=$?"
grep -E '^TW|Error|Traceback|line [0-9]+' "$WS/log/tw.log" | tail -20 | sed 's/^/  /'
