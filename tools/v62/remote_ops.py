"""Workspace-scoped SSH/SFTP operations; credentials are process environment only.

No global SSH config/key files, no recursive upload, no deletion, no overwrites.
Remote programs must be launched through a workspace-socket tmux session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import stat
from pathlib import Path

import paramiko

LOCAL = Path(r"D:\workspace\project1_database").resolve()
REMOTE = "/data/raw/huzijian/project1_database"
ACCOUNTS = {
    "wangzile": ("172.16.30.11", "PROJECT1_WANGZILE_SSH_PASSWORD"),
    "chenliang": ("172.16.30.12", "PROJECT1_CHENLIANG_SSH_PASSWORD"),
}
HOST_KEYS = {
    "172.16.30.11": "0534112d4de8eaac608e5afeefb3cd3791c000733657d2cff6a6e260580c82e0",
    "172.16.30.12": "d8e8b210914473d3d899a6d1df8c6b57134c54d347ef4dfe92d09efba2dd333c",
}


class ProjectHostPolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        if hashlib.sha256(key.asbytes()).hexdigest() != HOST_KEYS.get(hostname):
            raise paramiko.SSHException("SSH host key differs from project connection baseline")


def remote_path(value):
    path = posixpath.normpath(value)
    if not (path == REMOTE or path.startswith(REMOTE + "/")):
        raise ValueError("remote path outside authorized workspace")
    return path


def local_path(value):
    path = Path(value).resolve()
    if path != LOCAL and LOCAL not in path.parents:
        raise ValueError("local path outside authorized workspace")
    return path


def remote_checked(sftp, value):
    path = remote_path(value)
    # Reject symlink traversal out of the project, including parent components.
    # Start at the authorized root, never enumerate its ancestors.
    current = REMOTE
    remote_path(sftp.normalize(current))
    for part in path[len(REMOTE):].strip("/").split("/"):
        if not part:
            continue
        current = posixpath.join(current, part)
        try:
            entry = sftp.lstat(current)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(entry.st_mode):
            remote_path(sftp.normalize(current))
    return path


def ensure_directory(sftp, value):
    value = remote_checked(sftp, value)
    current = REMOTE
    for part in value[len(REMOTE):].strip("/").split("/"):
        if not part:
            continue
        current = posixpath.join(current, part)
        try:
            info = sftp.stat(current)
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("not a directory: " + current)
        except FileNotFoundError:
            sftp.mkdir(current)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["list", "put", "get", "tmux", "status", "read"])
    ap.add_argument("--account", choices=ACCOUNTS, required=True)
    ap.add_argument("--remote", required=True)
    ap.add_argument("--local")
    ap.add_argument("--session")
    ap.add_argument("--socket")
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--directories-only", action="store_true")
    ap.add_argument("--name-regex")
    ap.add_argument("--tail-lines", type=int, default=0)
    args = ap.parse_args()
    remote_path(args.remote)
    host, env_name = ACCOUNTS[args.account]
    password = os.environ.pop(env_name, None)
    if not password:
        raise SystemExit("SSH credential missing from current process")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(ProjectHostPolicy())
    client.connect(host, username=args.account, password=password,
                   timeout=args.timeout, auth_timeout=args.timeout,
                   banner_timeout=args.timeout, allow_agent=False, look_for_keys=False)
    password = None
    try:
        key = client.get_transport().get_remote_server_key()
        print(json.dumps({"host": host, "account": args.account,
                          "host_key_sha256_hex": hashlib.sha256(key.asbytes()).hexdigest()}), flush=True)
        with client.open_sftp() as sftp:
            path = remote_checked(sftp, args.remote)
            if args.action == "list":
                import re
                data = [{"name": a.filename, "bytes": a.st_size,
                         "directory": stat.S_ISDIR(a.st_mode),
                         "symlink": stat.S_ISLNK(a.st_mode)}
                        for a in sftp.listdir_attr(path)
                        if (not args.directories_only or stat.S_ISDIR(a.st_mode))
                        and (not args.name_regex or re.search(args.name_regex, a.filename))]
                print(json.dumps({"path": path, "entries": data}, ensure_ascii=False))
            elif args.action == "read":
                with sftp.open(path, "rb") as handle:
                    if args.tail_lines:
                        handle.seek(max(0, sftp.stat(path).st_size - 65536))
                    data = handle.read(512 * 1024 + 1)
                if len(data) > 512 * 1024:
                    raise ValueError("refuse oversized read; download specified artifact instead")
                result = data.decode("utf-8", errors="replace")
                print('\n'.join(result.splitlines()[-args.tail_lines:]) if args.tail_lines else result)
            elif args.action == "put":
                source = local_path(args.local)
                ensure_directory(sftp, posixpath.dirname(path))
                try:
                    sftp.lstat(path)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError("refuse overwrite: " + path)
                sftp.put(str(source), path)
                print(json.dumps({"uploaded": path, "bytes": source.stat().st_size}))
            elif args.action == "get":
                sftp.stat(path)
                target = local_path(args.local)
                if target.exists():
                    raise ValueError("refuse local overwrite: " + str(target))
                target.parent.mkdir(parents=True, exist_ok=True)
                sftp.get(path, str(target))
                print(json.dumps({"downloaded": str(target), "bytes": target.stat().st_size}))
            else:
                import shlex
                socket = remote_checked(sftp, args.socket)
                ensure_directory(sftp, posixpath.dirname(socket))
                if not args.session or not args.session.replace("_", "").isalnum():
                    raise ValueError("unsafe session name")
                # -f is an explicitly supplied in-workspace config, not a home config.
                config = remote_checked(sftp, REMOTE + "/tools/v62/tmux.conf")
                command = ["/usr/bin/tmux", "-S", socket, "-f", config]
                if args.action == "status":
                    command += ["capture-pane", "-p", "-t", args.session]
                else:
                    command += ["new-session", "-d", "-s", args.session,
                                "/bin/bash --noprofile --norc " + shlex.quote(path)]
                _, stdout, stderr = client.exec_command(
                    "cd " + shlex.quote(REMOTE) + " && "
                    + " ".join(shlex.quote(x) for x in command), timeout=args.timeout)
                out = stdout.read().decode("utf-8", errors="replace")
                err = stderr.read().decode("utf-8", errors="replace")
                rc = stdout.channel.recv_exit_status()
                print(json.dumps({"exit_code": rc, "stdout": out, "stderr": err,
                                  "session": args.session, "socket": socket}))
                if rc:
                    raise SystemExit(rc)
    finally:
        client.close()


if __name__ == "__main__":
    main()
