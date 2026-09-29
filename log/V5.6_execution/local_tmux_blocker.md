# V5.6 §9 execution boundary: local tmux cannot host a socket inside the workspace

Probed 2026-09-29 16:35 (+08:00) with `tools/v56/tmux_socket_probe.sh`. Raw output is below.

## 1. The requirement, and what it anticipated

V5.6 §9 requires that all project resources, caches, sockets and outputs stay inside
`D:\workspace\project1_database\` (local) or `/data/raw/huzijian/project1_database/` (server), that
long computations on both the server and locally go through tmux, and — specifically — that an
earlier V5.5 probe's habit of putting its socket and temporary scripts in WSL `/tmp` must **not** be
reused. It names `/mnt/d/workspace/project1_database/tmp/...` as the path to try and then instructs:

> 若该挂载不支持socket，不擅自退回工作区外；保留明确错误并报告该执行边界阻塞，同时推进服务器物理。

If the mount does not support sockets, do not retreat outside the workspace on one's own initiative;
keep a clear error and report the execution-boundary blocker, while continuing server physics.

## 2. Measured result: NOT SUPPORTED

```
tmux      : /usr/bin/tmux
tmux 3.4
dir created: yes
new-session rc=0 out=[error creating /mnt/d/workspace/project1_database/tmp/v56_tmux_probe/probe.sock (Operation not supported)]
socket file exists: NO (tmux reported success but no socket file is present)
command round-trip: FAILED (no output file)
RESULT: NOT_SUPPORTED (server starts but cannot execute a command)
```

The decisive line is `error creating ... (Operation not supported)`. `/mnt/d` is a 9p/DrvFs mount to
the Windows drive, and **Unix domain sockets are not supported on that mount type**. Two details
worth recording because they are exactly the kind of thing that gets misread as success:

1. **`new-session` returned rc=0 while failing.** The error text is on stdout and the exit code is
   zero. A script that checked only `$?` would have concluded the socket was created. The probe
   therefore also checks that the socket file exists and that a command can actually be sent and its
   output retrieved.
2. **The command round-trip failed too.** Even had the socket appeared, creating a server is not the
   same as being able to drive it. The probe verifies the full path by sending `echo` into the
   session and reading the file it writes; that file was never produced.

So the boundary is: **a local long-running job cannot be hosted in a tmux session whose socket lives
inside the workspace.** This is a real limit of the filesystem, not a configuration error, and no
amount of retrying changes it.

## 3. What this means for the plan, and what I am doing instead

This is reported as a blocker, not worked around. Specifically:

- I am **not** putting a socket in WSL `/tmp` or anywhere else outside the workspace. That was
  explicitly forbidden and remains forbidden.
- **The server side is unaffected.** Server tmux is ordinary Linux tmux on a normal filesystem and
  works; both physics solves (video A and video B) are being driven on the server.
- **Local long computations still run**, just not under tmux. The durable-execution need tmux serves
  is being met two other ways, and this is stated so the gap is explicit rather than papered over:
  1. long local jobs run as managed background jobs, whose output is captured to a log file inside
     the workspace and can be read at any time;
  2. the renderer is written to be **restartable rather than disposable**: `tools/v56/render.py`
     refuses to overwrite an existing frame and exits if frames are already present, and each frame
     is written as its own file with its own timing record. A render interrupted at any point can be
     resumed into a new run directory with the completed frames moved across, so losing the
     controlling process does not lose the work. The cost measurement already writes per-frame
     timings for exactly this purpose.

**The honest residual risk:** if the local machine reboots or the session ends, a local render
process dies with it, and there is no tmux to survive that. The restartable design reduces the loss
to the frames not yet written. Given the measured budget (§8.2: 1280×720 needs ~17.7 h of 21.5 h
remaining), an unplanned interruption is a genuine threat to the deadline, and it is recorded here as
a risk rather than discovered later.

## 4. What would remove the blocker

Any one of these, none of which is available within this task's constraints:

- a local tmux whose socket directory lives on a filesystem that supports Unix sockets (a native
  Linux path or a WSL-internal path) — forbidden by §9 because it leaves the workspace;
- WSL2 with the project on a Linux-native filesystem rather than a DrvFs mount;
- accepting that local durability is provided by restartable scripts instead of tmux, which is the
  position taken here and the reason the renderer is resumable.

## 5. Reproduction

```powershell
wsl.exe -e bash /mnt/d/workspace/project1_database/tools/v56/tmux_socket_probe.sh
```

The probe owns only its own directory (`tmp/v56_tmux_probe/`) and its own socket file, creates no
project data, and removes nothing but a stale copy of its own socket. No project file was deleted.
