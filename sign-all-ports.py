#!/usr/bin/env python3
"""
Signs every port in this collection with `pkgmk -us`, asking for the
signify passphrase ONCE and reusing it in memory for the rest of the run.

The passphrase is read with getpass (hidden input), held only in this
process's memory for the run, and fed straight into pkgmk's own `signify`
child over a pty whenever it prompts for it — it is never written to disk,
logged, or passed as a command-line argument (which would be visible to
other users via `ps`).

Caveat: Python strings are immutable, so the passphrase may linger in
freed memory until reused/garbage-collected; this is "good enough for a
single-user machine" convenience, not a hardened secrets flow.
"""
import getpass
import os
import pty
import select
import sys
from pathlib import Path

REPO_DIR = Path.home() / "d77crux"
SECKEY = Path.home() / "Downloads" / "d77crux.sec"
PORT_LOGS = REPO_DIR / ".sign-logs"


def run_signed(port_dir: Path, passphrase: str, log_path: Path) -> bool:
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(port_dir)
        os.execvp("pkgmk", ["pkgmk", "-d", "-us", "-sk", str(SECKEY)])
        os._exit(127)

    sent = False
    with open(log_path, "wb") as logf:
        while True:
            try:
                ready, _, _ = select.select([fd], [], [], 60)
            except OSError:
                break
            if not ready:
                break
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            logf.write(chunk)
            if not sent and b"passphrase" in chunk.lower():
                os.write(fd, (passphrase + "\n").encode())
                sent = True

    _, status = os.waitpid(pid, 0)
    return os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


def main() -> int:
    if not SECKEY.exists():
        print(f"Secret key not found: {SECKEY}", file=sys.stderr)
        return 1
    os.chmod(SECKEY, 0o600)

    passphrase = getpass.getpass(
        "Signify passphrase (kept in memory for this run only): "
    )

    PORT_LOGS.mkdir(exist_ok=True)
    ports = sorted(p for p in REPO_DIR.iterdir() if (p / "Pkgfile").is_file())

    ok = 0
    failed = []
    for port in ports:
        print(f"==> {port.name}")
        if run_signed(port, passphrase, PORT_LOGS / f"{port.name}.log"):
            ok += 1
        else:
            failed.append(port.name)

    del passphrase

    print(f"\nDone. OK={ok} FAIL={len(failed)}")
    print(f"Per-port logs: {PORT_LOGS}/<port>.log")
    if failed:
        print("\nFailed ports (check their log — likely dead/moved source URL):")
        for name in failed:
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
