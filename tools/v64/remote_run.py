"""V6.4 -- run a script on a project node through a project tmux socket.

WHY THIS EXISTS
---------------
The plan requires every solve, bake, model process and render to run on the server, launched through tmux with a
launcher that uses absolute paths (sections 10.1, 10.2), and it forbids re-using the old launchers because
`launch_gpu_stills.py` hardcodes an old UUID and an old output directory. `remote_ops.py` can start a tmux session
but only runs one pre-existing path and cannot pass arguments or choose an interpreter.

So this module owns exactly that job and nothing else:
  * upload a script and a generated launcher, refusing to overwrite either;
  * the launcher pins absolute paths, redirects every cache into a V6.4 scratch, and records its own exit code;
  * start it in a V6.4 tmux session on the V6.4 socket;
  * capture the pane and the log, and say whether the session is still alive.

Guarantees it enforces because the plan demands them:
  * every path is inside the authorised remote workspace (checked before use);
  * no overwrite anywhere -- a re-run must use a new name, so a previous run's evidence cannot be silently replaced;
  * the exit code is read from the log rather than inferred from a pane, so "the pane closed" is never mistaken for
    "the job succeeded";
  * scratch is per-node and per-run.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import shlex
import sys
from pathlib import Path

import paramiko

sys.path.insert(0, str(Path(r"D:\workspace\project1_database\tools\v62")))
from remote_ops import ACCOUNTS, HOST_KEYS, REMOTE, ProjectHostPolicy, remote_path  # noqa: E402

LOCAL_TOOLS = Path(r"D:\workspace\project1_database\tools\v64")
LOCAL_TOOLS.mkdir(parents=True, exist_ok=True)


def connect(account):
    host, env_name = ACCOUNTS[account]
    password = os.environ.get(env_name)
    if not password:
        raise SystemExit(f"missing process-env credential {env_name}")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(ProjectHostPolicy())
    client.connect(host, username=account, password=password, timeout=60,
                   allow_agent=False, look_for_keys=False)
    return client, host


def ssh(client, script, timeout=900):
    _, stdout, stderr = client.exec_command(script, timeout=timeout)
    rc = stdout.channel.recv_exit_status()
    return rc, stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")


def sftp_put_new(client, local, remote):
    """Upload, refusing to overwrite. Returns the byte count."""
    remote = remote_path(remote)
    with client.open_sftp() as sftp:
        try:
            sftp.stat(remote)
        except FileNotFoundError:
            pass
        else:
            raise SystemExit(f"refuse overwrite: {remote} already exists; use a new revision name")
        ensure = posixpath.dirname(remote)
        parts = ensure[len(REMOTE):].strip("/").split("/")
        cur = REMOTE
        for part in parts:
            if not part:
                continue
            cur = posixpath.join(cur, part)
            remote_path(cur)
            try:
                sftp.stat(cur)
            except FileNotFoundError:
                sftp.mkdir(cur)
        sftp.put(str(local), remote)
    return Path(local).stat().st_size


def build_launcher(name, script_path, interpreter, args, scratch, log_path):
    """Generate the launcher. Every path absolute; caches pinned to the V6.4 scratch.

    The Blender wrapper is mode `-rw-rw-rw-` -- it carries no execute bit, so invoking it directly fails with
    `Permission denied` and exit 126. The V6.3 launchers all call it as `/bin/bash --noprofile --norc <wrapper>`,
    which is what this does too, rather than chmod-ing a shared project file.

    `--python-exit-code 2` is carried over from the V6.3 launchers deliberately: without it Blender reports success
    even when the Python script raised, which would let a failed diagnosis look like a passing one.
    """
    if interpreter == "blender":
        exe = (f"/bin/bash --noprofile --norc {REMOTE}/tools/v62/blender42_scoped.sh "
               f"--background --factory-startup --disable-autoexec --threads 8 --python-exit-code 2 "
               f"--python {shlex.quote(script_path)}")
        if args:
            exe += " -- " + args
    elif interpreter == "python":
        # `-u` is not cosmetic: the launcher appends stdout to a log file, so without it a long solve's progress is
        # block-buffered and the log stays empty for many minutes, which is indistinguishable from a hang.
        exe = f"{REMOTE}/tools/conda_env/bin/python -B -u {shlex.quote(script_path)}"
        if args:
            exe += " " + args
    else:
        raise SystemExit(f"unknown interpreter {interpreter}")
    return f"""#!/bin/bash
# V6.4 launcher -- generated. Do not edit; generate a new revision instead.
set -u
ulimit -c 0
cd {REMOTE}
export V62_SCRATCH={shlex.quote(scratch)}
export TMPDIR={shlex.quote(scratch)}
export TEMP={shlex.quote(scratch)}
export TMP={shlex.quote(scratch)}
export XDG_CACHE_HOME={shlex.quote(scratch)}/cache
export XDG_CONFIG_HOME={shlex.quote(scratch)}/config
export XDG_DATA_HOME={shlex.quote(scratch)}/data
export CUDA_CACHE_PATH={shlex.quote(scratch)}/cuda_cache
export OPTIX_CACHE_PATH={shlex.quote(scratch)}/optix_cache
export __GL_SHADER_DISK_CACHE_PATH={shlex.quote(scratch)}/gl_shader_cache
export MESA_SHADER_CACHE_DIR={shlex.quote(scratch)}/mesa_shader_cache
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
/usr/bin/mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" \\
  "$CUDA_CACHE_PATH" "$OPTIX_CACHE_PATH" "$__GL_SHADER_DISK_CACHE_PATH" "$MESA_SHADER_CACHE_DIR"
: > {shlex.quote(log_path)}
echo "LAUNCHER_START $(date -u +%Y-%m-%dT%H:%M:%SZ) name={name}" >> {shlex.quote(log_path)}
{exe} >> {shlex.quote(log_path)} 2>&1
rc=$?
echo "EXIT_CODE=$rc" >> {shlex.quote(log_path)}
echo "LAUNCHER_END $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> {shlex.quote(log_path)}
exit $rc
"""


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "capture", "log", "kill", "sessions"])
    ap.add_argument("--account", required=True, choices=sorted(ACCOUNTS))
    ap.add_argument("--name", help="run name; becomes the tmux session and the launcher name")
    ap.add_argument("--script", help="local script path to upload")
    ap.add_argument("--remote-script", help="skip upload and use this existing remote script")
    ap.add_argument("--interpreter", default="blender", choices=["blender", "python"])
    ap.add_argument("--args", default="")
    # deliberately re-upload the main script even if the node already has a byte-identical copy. Needed only when
    # re-running the same case file unchanged; a genuinely edited script still must be given a new revision name.
    ap.add_argument("--rerun", action="store_true")
    ap.add_argument("--run-id", default="v64_20261006_p0")
    ap.add_argument("--tail", type=int, default=80)
    # shared modules to upload alongside the entry script (repeatable)
    ap.add_argument("--also", action="append",
                    help="additional local file to upload into tools/v64 on the node (repeatable)")
    args = ap.parse_args()

    host, _ = ACCOUNTS[args.account]
    node = host.split(".")[-1]
    socket = remote_path(f"{REMOTE}/tmp/v64_node{node}_control.sock")
    scratch = remote_path(f"{REMOTE}/tmp/v64_{node}_{args.run_id}")
    client, host = connect(args.account)
    try:
        if hashlib.sha256(client.get_transport().get_remote_server_key().asbytes()).hexdigest() != HOST_KEYS[host]:
            raise SystemExit("host key mismatch")

        if args.action == "sessions":
            rc, out, err = ssh(client, f"/usr/bin/tmux -S {shlex.quote(socket)} list-sessions 2>&1 || true")
            print(out.strip() or "(no sessions)")
            return

        if args.action in ("capture", "log", "kill"):
            if not args.name or not args.name.replace("_", "").isalnum():
                raise SystemExit("unsafe or missing --name")
            if args.action == "kill":
                rc, out, err = ssh(client, f"/usr/bin/tmux -S {shlex.quote(socket)} kill-session "
                                           f"-t {shlex.quote(args.name)} 2>&1 || true")
                print(f"kill: {out.strip()}")
                return
            if args.action == "capture":
                rc, out, err = ssh(client, f"/usr/bin/tmux -S {shlex.quote(socket)} has-session "
                                           f"-t {shlex.quote(args.name)} 2>/dev/null && echo ALIVE || echo GONE")
                alive = "ALIVE" in out
                rc, out2, _ = ssh(client, f"/usr/bin/tmux -S {shlex.quote(socket)} capture-pane -p "
                                          f"-t {shlex.quote(args.name)} 2>&1 | tail -{args.tail}")
                print(json.dumps({"session": args.name, "alive": alive,
                                  "pane_tail": out2}, ensure_ascii=False))
                return
            # log
            log_path = remote_path(f"{REMOTE}/log/V6.4_execution/{args.name}.log")
            rc, out, err = ssh(client, f"test -f {shlex.quote(log_path)} && tail -{args.tail} "
                                       f"{shlex.quote(log_path)} || echo 'NO LOG YET'")
            done = "EXIT_CODE=" in out
            code = None
            for line in out.splitlines():
                if line.startswith("EXIT_CODE="):
                    code = int(line.split("=", 1)[1])
            print(json.dumps({"session": args.name, "log": log_path, "finished": done,
                              "exit_code": code, "tail": out}, ensure_ascii=False))
            return

        # ---- run ----
        if not args.name or not args.name.replace("_", "").isalnum():
            raise SystemExit("unsafe or missing --name")
        # shared modules are uploaded too, and deliberately so: the launcher runs with cwd=REMOTE, but a module
        # living only in tools/v64 on the local machine would make the remote script fail at import with no clue
        # that the cause was a missing sibling file rather than a physics problem.
        #
        # An UNCHANGED module is skipped rather than refused. The no-overwrite rule exists to stop a new revision
        # from silently replacing evidence a previous run depended on; re-uploading a byte-identical file is not
        # that, and forcing a new name for it would litter tools/v64 with copies that differ in nothing. A module
        # whose content actually changed still has to be renamed by hand, which is the case the rule is for.
        for extra in (args.also or []):
            ep = Path(extra).resolve()
            if not ep.exists():
                raise SystemExit(f"no such local module: {ep}")
            remote_mod = remote_path(f"{REMOTE}/tools/v64/{ep.name}")
            local_bytes = ep.read_bytes()
            local_sha = hashlib.sha256(local_bytes).hexdigest()
            identical = False
            with client.open_sftp() as sftp:
                try:
                    with sftp.open(remote_mod, "rb") as handle:
                        identical = (hashlib.sha256(handle.read()).hexdigest() == local_sha)
                except FileNotFoundError:
                    pass
            if identical:
                print(f"module {ep.name} unchanged on node (sha256 {local_sha[:12]}), not re-uploaded")
                continue
            n = sftp_put_new(client, ep, remote_mod)
            print(f"uploaded module {ep.name} ({n} bytes, sha256 {local_sha[:12]})")
        if args.script:
            local = Path(args.script).resolve()
            if not local.exists():
                raise SystemExit(f"no such local script: {local}")
            remote_script = remote_path(f"{REMOTE}/tools/v64/{local.name}")
            # Same rule as for shared modules above, and for the same reason: re-running the SAME script with
            # DIFFERENT arguments is a normal thing to do (this is how the per-case causal runs work), and the
            # no-overwrite guard is about not silently replacing evidence, which a byte-identical file cannot do.
            # A changed script still has to be renamed; `--rerun` exists for deliberately re-running one case
            # against the identical file that is already on the node.
            local_bytes = local.read_bytes()
            local_sha = hashlib.sha256(local_bytes).hexdigest()
            identical = False
            if not args.rerun:
                with client.open_sftp() as sftp:
                    try:
                        with sftp.open(remote_script, "rb") as handle:
                            identical = (hashlib.sha256(handle.read()).hexdigest() == local_sha)
                    except FileNotFoundError:
                        pass
            if identical:
                print(f"script {local.name} unchanged on node (sha256 {local_sha[:12]}), reusing it")
            else:
                n = sftp_put_new(client, local, remote_script)
                print(f"uploaded {local.name} ({n} bytes) -> {remote_script}")
        elif args.remote_script:
            remote_script = remote_path(args.remote_script)
            rc, out, _ = ssh(client, f"test -f {shlex.quote(remote_script)} && echo OK || echo MISSING")
            if "OK" not in out:
                raise SystemExit(f"remote script missing: {remote_script}")
        else:
            raise SystemExit("need --script or --remote-script")

        log_path = remote_path(f"{REMOTE}/log/V6.4_execution/{args.name}.log")
        launcher_body = build_launcher(args.name, remote_script, args.interpreter, args.args, scratch, log_path)
        launcher_remote = remote_path(f"{REMOTE}/tools/v64/launch_{args.name}.sh")
        with client.open_sftp() as sftp:
            try:
                sftp.stat(launcher_remote)
            except FileNotFoundError:
                pass
            else:
                raise SystemExit(f"refuse overwrite of launcher: {launcher_remote}; use a new --name")
            with sftp.open(launcher_remote, "wb") as handle:
                handle.write(launcher_body.encode("utf-8"))
        print(f"wrote launcher {launcher_remote}")

        # start in a fresh session; a stale session name must not be silently reused
        rc, out, err = ssh(client, f"/usr/bin/tmux -S {shlex.quote(socket)} has-session "
                                   f"-t {shlex.quote(args.name)} 2>/dev/null && echo EXISTS || echo FREE")
        if "EXISTS" in out:
            raise SystemExit(f"tmux session {args.name} already exists; use a new --name")
        # tmux 1.8 accepts exactly ONE `command` argument for new-session; passing the interpreter and its flags as
        # separate argv entries is rejected with a usage message. The whole command must therefore be a single
        # shell-quoted string. `-f` is accepted, and must precede the subcommand.
        whole = f"/bin/bash --noprofile --norc {launcher_remote}"
        rc, out, err = ssh(
            client,
            f"cd {shlex.quote(REMOTE)} && /usr/bin/tmux -S {shlex.quote(socket)} "
            f"-f {REMOTE}/tools/v62/tmux.conf new-session -d -s {shlex.quote(args.name)} "
            f"{shlex.quote(whole)}")
        if rc != 0:
            raise SystemExit(f"tmux new-session failed (rc={rc}): {err.strip() or out.strip()}")
        print(f"started session {args.name} on {socket}")
        print(json.dumps({"session": args.name, "socket": socket, "log": log_path,
                          "launcher": launcher_remote, "script": remote_script,
                          "scratch": scratch}, ensure_ascii=False))
    finally:
        client.close()


if __name__ == "__main__":
    main()
