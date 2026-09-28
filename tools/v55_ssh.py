#!/usr/bin/env python
"""Run ``tools/ssh_ctl.py`` with the project password injected into the CHILD
process environment only.

Why this exists
---------------
``tools/ssh_ctl.py`` reads the SSH password from an environment variable.  The
value lives in ``log/key.txt``, whose own layout documents one credential per
line as::

    ssh <user>@<host> 密码 <password>

The password is the FINAL whitespace-separated token on that line.  This module
never prints, logs, or stores it: it is read at call time and placed only in the
child process environment.

Usage
-----
    python tools/v55_ssh.py check
    python tools/v55_ssh.py run --cmd "hostname"
    python tools/v55_ssh.py put --local a.sh --remote /data/.../a.sh
    python tools/v55_ssh.py get --remote /data/.../a.log --local a.log

``check`` prints only whether the credential line was found and how many
characters it holds -- never the value.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SSH_CTL = ROOT / "tools" / "ssh_ctl.py"
KEY = ROOT / "log" / "key.txt"

#: account -> (host recorded in the key file, env var ssh_ctl.py expects)
ACCOUNTS = {
    "wangzile": ("172.16.30.11", "PROJECT1_WANGZILE_SSH_PASSWORD"),
    "chenliang": ("172.16.30.12", "PROJECT1_CHENLIANG_SSH_PASSWORD"),
}


def key_text() -> str:
    """Decode key.txt.  The file is not guaranteed to be UTF-8."""
    raw = KEY.read_bytes()
    for encoding in ("utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"could not decode {KEY}")


def password_for(account: str) -> tuple[str, str]:
    """Return (env_var_name, password) for ``account``.

    The key file documents one credential per line as
    ``ssh <user>@<host> 密码 <password>``; the password is the final
    whitespace-separated token.  We match on the ``user@host`` pair rather than
    line number so the file can be edited without silently using the wrong
    secret, and we never assume the whole file is one password.
    """
    if account not in ACCOUNTS:
        raise SystemExit(f"unknown account {account!r}; known: {sorted(ACCOUNTS)}")
    host, env_name = ACCOUNTS[account]
    needle = f"{account}@{host}"
    for line in key_text().splitlines():
        if needle not in line:
            continue
        tokens = line.split()
        if len(tokens) >= 2:
            return env_name, tokens[-1]
    raise SystemExit(f"no credential line matching {needle!r} in {KEY}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    account = os.environ.get("V55_SSH_ACCOUNT", "wangzile")
    env_name, password = password_for(account)

    if argv[1] == "check":
        print(f"account      : {account}")
        print(f"key file     : {KEY}")
        print(f"env var      : {env_name}")
        print(f"password len : {len(password)} chars (value not printed)")
        print(f"ssh_ctl      : {SSH_CTL} (exists={SSH_CTL.is_file()})")
        return 0

    env = dict(os.environ)
    env[env_name] = password
    # Keep the child from inheriting any stale credential for the other account.
    for other, (_, other_env) in ACCOUNTS.items():
        if other != account:
            env.pop(other_env, None)

    cmd = [sys.executable, str(SSH_CTL), *argv[1:]]
    try:
        return subprocess.call(cmd, env=env, cwd=str(ROOT))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
