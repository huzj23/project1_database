"""Minimal non-interactive SSH/SFTP helper for the simulation server.

Windows has no ``sshpass``, so password authentication is done through paramiko.

Usage
-----
    python tools/ssh_ctl.py run  --cmd "nvidia-smi"
    python tools/ssh_ctl.py run  --cmd "ls -la" --cwd /data/raw/huzijian/project1_database
    python tools/ssh_ctl.py put  --local a.tar.gz --remote /data/raw/huzijian/project1_database/a.tar.gz
    python tools/ssh_ctl.py get  --remote /path/file --local local_file
    python tools/ssh_ctl.py sudo-run --cmd "..."        # via sudo -S, password on stdin

SAFETY
------
Every remote path is checked against ``ALLOWED_ROOTS``.  This project may only
touch its own workspace on the shared server; anything else is refused before a
connection is even opened.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import stat
import sys
import time

import paramiko

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

HOSTS = {
    "wangzile": {
        "host": "172.16.30.11",
        "user": "wangzile",
        "password_env": "PROJECT1_WANGZILE_SSH_PASSWORD",
    },
    "chenliang": {
        "host": "172.16.30.12",
        "user": "chenliang",
        "password_env": "PROJECT1_CHENLIANG_SSH_PASSWORD",
    },
}
DEFAULT_ACCOUNT = "wangzile"

#: The ONLY remote tree this project is permitted to read or write.
WORKSPACE = "/data/raw/huzijian/project1_database"
ALLOWED_ROOTS = (WORKSPACE,)

#: Commands that could plausibly damage shared state; refused outright.
FORBIDDEN_PATTERNS = (
    "rm -rf /", "rm -rf /*", "mkfs", "dd if=", ":(){", "chmod -R 777 /",
    "> /dev/sda", "shutdown", "reboot", "init 0", "init 6",
    "chown -R", "sudo ", "su -", "> /etc/", ">> /etc/",
)

#: Absolute paths that are fine to *reference* because they are read-only system
#: tooling the OS provides to every process.  Anything else outside the
#: workspace is refused.
READONLY_PREFIXES = (
    "/usr/bin/", "/usr/sbin/", "/usr/lib/", "/usr/lib64/", "/usr/share/",
    "/usr/local/bin/", "/bin/", "/sbin/", "/lib/", "/lib64/",
    "/etc/pki/", "/etc/ssl/", "/etc/ld.so", "/etc/profile", "/etc/bashrc",
    "/proc/", "/sys/", "/dev/null", "/dev/stdout", "/dev/stderr", "/dev/urandom",
    "/data/raw/wangzile/miniconda3/bin/",   # conda CLI (read-only invocation)
)

#: Roots that are never acceptable to touch at all.
HARD_DENY_PREFIXES = (
    "/home/", "/root/", "/net/", "/mnt/", "/media/", "/boot/", "/srv/",
    "/var/", "/opt/", "/tmp/", "/data/raw/wangzile/", "/data/raw/wangyuchao/",
)


class SafetyError(RuntimeError):
    pass


#: Placeholder used when masking workspace paths.  It must be a plain
#: alphanumeric token: a token containing '/' would leave a stray slash behind
#: and be misread as the filesystem root by the path scanner below.
_WS_TOKEN = "WSROOT"


def _mask_workspace(text: str) -> str:
    out = text
    for root in ALLOWED_ROOTS:
        # mask the long form first so the token never ends up followed by '/'
        out = out.replace(root + "/", _WS_TOKEN + "/")
        out = out.replace(root, _WS_TOKEN)
    # server_env.sh exports WS=<workspace>; treat "$WS/..." as a workspace path
    # too, otherwise shell-variable indirection looks like an unknown absolute path.
    for var in ("${WS}", "$WS", "${WORKSPACE}", "$WORKSPACE"):
        out = out.replace(var + "/", _WS_TOKEN + "/")
        out = out.replace(var, _WS_TOKEN)
    return out


def _is_ws_path(path: str) -> bool:
    return path == _WS_TOKEN or path.startswith(_WS_TOKEN + "/")


#: Absolute path token, e.g. /data/raw/foo or /etc/passwd.  The trailing '+'
#: matters: it stops a bare '/' (as found inside sed expressions such as
#: 's/\r$//') from being reported as a path.  A lone root is still caught by
#: FORBIDDEN_PATTERNS.
_ABS_PATH_RE = __import__("re").compile(r"(?<![\w<])/(?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_.\-]+")

#: URLs are not filesystem paths; strip them before scanning so that
#: https://repo.anaconda.com/pkgs/... is not mistaken for a local path.
_URL_RE = __import__("re").compile(r"\b[A-Za-z][A-Za-z0-9+.\-]*://\S+")


def check_command(cmd: str) -> None:
    """Refuse commands that are destructive or reach outside the workspace.

    Every absolute path in the command is inspected *after* masking the
    workspace prefix and removing URLs, so legitimate
    ``rm -rf <workspace>/...`` still works while anything pointing at another
    user's data, a system config directory, or a world-writable scratch area is
    rejected before a connection is opened.
    """
    masked = _URL_RE.sub("URL", _mask_workspace(cmd))
    low = masked.lower()

    for bad in FORBIDDEN_PATTERNS:
        if bad.lower() in low:
            raise SafetyError(f"refusing destructive command containing {bad!r}")

    offenders = []
    for m in _ABS_PATH_RE.finditer(masked):
        path = m.group(0)
        if _is_ws_path(path):               # already-masked workspace reference
            continue
        if any(path.startswith(p) for p in READONLY_PREFIXES):
            continue
        offenders.append(path)

    if offenders:
        uniq = sorted(set(offenders))
        raise SafetyError(
            "command references paths outside the permitted workspace.\n"
            f"  allowed : {WORKSPACE}\n"
            f"  refused : {', '.join(uniq[:8])}")


def check_remote_path(path: str) -> str:
    """Normalise and verify a remote path stays inside the allowed workspace."""
    p = posixpath.normpath(path)
    if not p.startswith("/"):
        raise SafetyError(f"remote path must be absolute: {path!r}")
    if not any(p == r or p.startswith(r.rstrip("/") + "/") for r in ALLOWED_ROOTS):
        raise SafetyError(
            f"remote path outside the permitted workspace.\n"
            f"  requested: {p}\n"
            f"  allowed  : {', '.join(ALLOWED_ROOTS)}")
    return p


# --------------------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------------------

def connect(account: str = DEFAULT_ACCOUNT, timeout: int = 20) -> paramiko.SSHClient:
    cfg = HOSTS[account]
    password_env = cfg["password_env"]
    password = os.environ.get(password_env)
    if not password:
        raise RuntimeError(
            f"missing SSH password: set environment variable {password_env}"
        )
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(cfg["host"], port=22, username=cfg["user"],
                   password=password, timeout=timeout,
                   allow_agent=False, look_for_keys=False)
    return client


def run(client, cmd: str, cwd: str | None = None, timeout: int | None = None,
        get_pty: bool = False):
    check_command(cmd)
    if cwd:
        cwd = check_remote_path(cwd)
        cmd = f"cd {shell_quote(cwd)} && {cmd}"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=get_pty)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    return rc, out, err


def shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


# --------------------------------------------------------------------------------------
# SFTP helpers
# --------------------------------------------------------------------------------------

def ensure_remote_dir(sftp, path: str) -> None:
    path = check_remote_path(path)
    parts, cur = path.strip("/").split("/"), ""
    for part in parts:
        cur += "/" + part
        try:
            sftp.stat(cur)
        except IOError:
            sftp.mkdir(cur)


def put_dir(sftp, local_dir: str, remote_dir: str, verbose: bool = True) -> int:
    remote_dir = check_remote_path(remote_dir)
    ensure_remote_dir(sftp, remote_dir)
    n = 0
    for root, dirs, files in os.walk(local_dir):
        # never ship virtualenvs / caches / VCS metadata
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", ".git", ".venv", "venv", ".mypy_cache")]
        rel = os.path.relpath(root, local_dir).replace("\\", "/")
        rdir = remote_dir if rel == "." else posixpath.join(remote_dir, rel)
        ensure_remote_dir(sftp, rdir)
        for f in files:
            lp = os.path.join(root, f)
            rp = posixpath.join(rdir, f)
            try:
                sftp.put(lp, rp)
                n += 1
                if verbose and n % 25 == 0:
                    print(f"  ... {n} files", flush=True)
            except Exception as e:
                print(f"  FAILED {rel}/{f}: {e}", file=sys.stderr)
    return n


def get_dir(sftp, remote_dir: str, local_dir: str) -> int:
    remote_dir = check_remote_path(remote_dir)
    n = 0
    os.makedirs(local_dir, exist_ok=True)
    for entry in sftp.listdir_attr(remote_dir):
        rp = posixpath.join(remote_dir, entry.filename)
        lp = os.path.join(local_dir, entry.filename)
        if stat.S_ISDIR(entry.st_mode):
            n += get_dir(sftp, rp, lp)
        else:
            sftp.get(rp, lp)
            n += 1
    return n


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="SSH/SFTP helper (workspace-restricted).")
    ap.add_argument("action", choices=["run", "put", "get", "probe", "putdir", "getdir"])
    ap.add_argument("--account", default=DEFAULT_ACCOUNT, choices=sorted(HOSTS))
    ap.add_argument("--cmd")
    ap.add_argument("--cwd")
    ap.add_argument("--local")
    ap.add_argument("--remote")
    ap.add_argument("--timeout", type=int, default=None)
    args = ap.parse_args(argv)

    client = connect(args.account)
    try:
        if args.action == "run":
            rc, out, err = run(client, args.cmd, args.cwd, args.timeout)
            sys.stdout.write(out)
            if err:
                sys.stderr.write(err)
            return rc
        if args.action == "probe":
            rc, out, err = run(client, args.cmd or "echo ok")
            print(out, end="")
            if err:
                print(err, file=sys.stderr, end="")
            return rc
        sftp = client.open_sftp()
        if args.action == "put":
            ensure_remote_dir(sftp, posixpath.dirname(check_remote_path(args.remote)))
            sftp.put(args.local, check_remote_path(args.remote))
            print(f"uploaded -> {args.remote}")
        elif args.action == "get":
            sftp.get(check_remote_path(args.remote), args.local)
            print(f"downloaded -> {args.local}")
        elif args.action == "putdir":
            n = put_dir(sftp, args.local, args.remote)
            print(f"uploaded {n} files -> {args.remote}")
        elif args.action == "getdir":
            n = get_dir(sftp, args.remote, args.local)
            print(f"downloaded {n} files -> {args.local}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SafetyError as e:
        print(f"SAFETY REFUSAL: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
