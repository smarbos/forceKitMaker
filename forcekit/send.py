"""Send an exported program to the Force over SSH.

The Force has ssh, tar and sftp-server but no rsync. A program folder is streamed as a tar
archive into one ssh call that extracts it into a temporary folder and only then replaces
the previous copy, so a dropped connection never leaves a half-copied kit.
"""
from __future__ import annotations

import io
import shlex
import subprocess
import tarfile
from pathlib import Path

from .config import Config

CONNECT_TIMEOUT = 6  # seconds
MARKER = ".forcekit-complete"
COPY_TIMEOUT = 600


class ForceError(Exception):
    """The Force couldn't be reached, logged into, or written to."""


class SendExists(Exception):
    def __init__(self, path: str):
        super().__init__(path)
        self.path = path


def _ssh(cfg: Config, command: str, data: bytes | None = None, timeout: float = 30) -> str:
    argv = [*cfg.ssh_command, "-o", "BatchMode=yes", "-o", f"ConnectTimeout={CONNECT_TIMEOUT}",
            # notice a dead Wi-Fi link in ~15 s instead of waiting for COPY_TIMEOUT
            "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3",
            f"{cfg.force_user}@{cfg.force_host}", command]
    try:
        r = subprocess.run(argv, input=data if data is not None else b"", capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ForceError(f"The Force at {cfg.force_host} stopped responding") from None
    except OSError as e:
        raise ForceError(f"Can't run ssh: {e}") from None
    if r.returncode == 255:  # ssh itself failed: unreachable or login refused
        detail = r.stderr.decode(errors="replace").strip().splitlines()
        hint = detail[-1] if detail else "no answer"
        raise ForceError(f"Can't connect to the Force at {cfg.force_user}@{cfg.force_host} ({hint}). "
                         f"Is it on and on Wi-Fi? Check the IP in Settings. If the login is refused, run "
                         f"ssh-copy-id {cfg.force_user}@{cfg.force_host} once in a terminal.")
    if r.returncode != 0:
        detail = r.stderr.decode(errors="replace").strip()
        raise ForceError(f"The Force reported an error: {detail or 'exit code ' + str(r.returncode)}")
    return r.stdout.decode(errors="replace")


def test_connection(cfg: Config) -> str:
    """Check login and that the forcekit folder can be created; return its free-space line."""
    d = shlex.quote(cfg.force_dir)
    out = _ssh(cfg, f"mkdir -p {d} && test -w {d} && df -h {d} | tail -n 1")
    return out.strip()


test_connection.__test__ = False  # not a pytest test despite the name


def _tar_stream(folder: Path) -> bytes:
    buf = io.BytesIO()

    def as_root(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        return info

    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as tar:
        tar.add(folder, arcname=folder.name, filter=as_root)
        # Last member: proves the whole archive arrived. tar exits 0 when its input ends
        # exactly between two files, so its exit code alone can't tell a cut copy from a full one.
        marker = as_root(tarfile.TarInfo(f"{folder.name}/{MARKER}"))
        tar.addfile(marker, io.BytesIO(b""))
    return buf.getvalue()


def send_program(cfg: Config, folder: Path, overwrite: bool = False) -> str:
    """Copy a local program folder (…/Drums/<Name>) to <force_dir>/Drums/<Name>; return the remote path."""
    folder = Path(folder)
    if folder.name in ("", ".", "..") or folder.parent.name in ("", ".", ".."):
        raise ValueError(f"not a program folder: {folder}")
    type_dir = f"{cfg.force_dir.rstrip('/')}/{folder.parent.name}"
    target = f"{type_dir}/{folder.name}"
    q = shlex.quote
    if not overwrite and _ssh(cfg, f"test -e {q(target)} && echo yes || echo no").strip() == "yes":
        raise SendExists(target)
    script = (
        f"T={q(type_dir)}; N={q(folder.name)}; S=\"$T/.$N.forcekit-tmp\"; "
        'mkdir -p "$T" && rm -rf "$S" && mkdir "$S" && tar -xf - -C "$S" '
        f'&& {{ [ -f "$S/$N/{MARKER}" ] || {{ echo "copy incomplete (connection lost?)" >&2; false; }}; }} '
        f'&& rm "$S/$N/{MARKER}" && rm -rf "$T/$N" && mv "$S/$N" "$T/$N"; rc=$?; rm -rf "$S"; exit $rc'
    )
    _ssh(cfg, script, data=_tar_stream(folder), timeout=COPY_TIMEOUT)
    return target
