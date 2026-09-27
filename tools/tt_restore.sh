#!/usr/bin/env bash
# My regex surgery mangled the carry config (it replaced from the wrong anchor).
# Restore from the .pre_eleph backups I took, then show the real structure so I can
# do a precise, non-destructive edit.
WS=/data/raw/huzijian/project1_database
REPO="$WS/code/physics-video-sim/physics-video-sim-main"
cd "$REPO" || exit 1

echo "=== restore ==="
for f in configs/scenarios/turntable_carry_gso.yaml configs/scenarios/turntable_spin_gso.yaml; do
  if [ -f "$f.pre_eleph" ]; then
    cp "$f.pre_eleph" "$f"
    echo "  restored $f ($(wc -l < $f) lines)"
  fi
done

echo
echo "=== carry: top-level keys and their line numbers ==="
grep -nE '^[a-z_]+:' configs/scenarios/turntable_carry_gso.yaml | sed 's/^/  /'

echo
echo "=== carry: exact camera block ==="
awk '/^camera:/{f=1} f{print NR": "$0} /^output:/{if(f)exit}' configs/scenarios/turntable_carry_gso.yaml | sed 's/^/  /'

echo
echo "=== carry: selection block ==="
awk '/^selection:/{f=1} f{print NR": "$0} /^timing:/{if(f)exit}' configs/scenarios/turntable_carry_gso.yaml | sed 's/^/  /'

echo
echo "=== spin: exact camera block ==="
awk '/^camera:/{f=1} f{print NR": "$0} /^output:/{if(f)exit}' configs/scenarios/turntable_spin_gso.yaml | sed 's/^/  /'

echo
echo "=== spin: selection block ==="
awk '/^selection:/{f=1} f{print NR": "$0} /^timing:/{if(f)exit}' configs/scenarios/turntable_spin_gso.yaml | sed 's/^/  /'

echo
echo "=== both parse? ==="
"$WS/tools/conda_env/bin/python" -c "
import yaml
for n in ('turntable_carry_gso','turntable_spin_gso'):
    d=yaml.safe_load(open(f'configs/scenarios/{n}.yaml'))
    print(f'  {n}: keys={list(d.keys())}')
    print(f'    policy={d[\"camera\"][\"policy\"]} actors={d[\"selection\"][\"asset_ids\"]}')
"
