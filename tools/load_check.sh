#!/usr/bin/env bash
# Is the shared node busy right now?  Reports GPU, CPU, memory and the top
# CPU consumers so we can decide whether to launch a batch.
export LC_ALL=C

echo "================= node load $(date '+%F %T') ================="

echo
echo "--- GPU ---"
nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu \
           --format=csv,noheader 2>/dev/null | sed 's/^/  /'

echo
echo "--- GPU compute processes (owner + memory) ---"
nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader 2>/dev/null |
  head -10 | sed 's/^/  /' || echo "  (none)"

echo
echo "--- CPU / memory ---"
uptime | sed 's/^/  /'
echo "  cores: $(nproc)"
free -g | head -2 | sed 's/^/  /'

echo
echo "--- top 12 CPU consumers (all users) ---"
ps -eo user,pid,pcpu,pmem,etime,comm --sort=-pcpu 2>/dev/null | head -13 | sed 's/^/  /'

echo
echo "--- my own processes ---"
n=$(ps -eo cmd 2>/dev/null | grep -c '[c]onda_env/bin/python')
echo "  my python processes: $n"
tmux ls 2>/dev/null | grep -E '^phyco_' | sed 's/^/  /' || echo "  (no phyco tmux sessions)"
echo "============================================================="
