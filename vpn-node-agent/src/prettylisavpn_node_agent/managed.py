"""Bounded, isolated REALITY authorizations. No destinations or payloads are logged."""

import hashlib
import json
import os
import select
import signal
import sqlite3
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID


class ManagedUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ManagedLease:
    id: UUID
    secret: str = field(repr=False)
    expires: int

    def validate(self, now: int) -> None:
        if str(UUID(self.secret)) != self.secret or not now < self.expires <= now + 1200:
            raise ValueError("invalid managed lease")


class ManagedProcess(Protocol):
    pid: int

    def poll(self) -> int | None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float) -> int: ...


class ProcessLauncher:
    """Fixed executable, private pipe, no shell, private config file or diagnostics."""

    def __init__(self, executable: Path) -> None:
        self.executable = executable

    def __call__(self, config: dict[str, Any]) -> ManagedProcess:
        child = subprocess.Popen(
            [str(self.executable), "--lease", config["id"]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        try:
            assert child.stdin is not None and child.stdout is not None
            child.stdin.write(json.dumps(config).encode() + b"\n")
            child.stdin.flush()
            ready, _, _ = select.select([child.stdout], [], [], 8)
            if not ready or child.stdout.readline(32) != b"READY\n" or child.poll() is not None:
                raise ManagedUnavailable
            return child
        except Exception:
            child.kill()
            child.wait(timeout=5)
            if child.stdin is not None:
                child.stdin.close()
            if child.stdout is not None:
                child.stdout.close()
            raise ManagedUnavailable("managed engine unavailable") from None

    def remove_orphan(self, pid: int, lease_id: str) -> None:
        # pidfd prevents signaling a different process if the PID is recycled.
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            return
        try:
            expected = [str(self.executable).encode(), b"--lease", lease_id.encode(), b""]
            try:
                command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
            except FileNotFoundError:
                return
            if command != expected:
                return  # The owned process has exited; this PID belongs to something else.
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except ProcessLookupError:
                return
            if not select.select([fd], [], [], 5)[0]:
                raise ManagedUnavailable("managed cleanup unconfirmed")
        finally:
            os.close(fd)


class ManagedController:
    """SQLite records idempotency/tombstones; PostgreSQL remains account authority.

    One process per authorization intentionally bounds the first deployment's
    capacity. Removing one authorization cannot interrupt another user's tunnel.
    """

    def __init__(
        self,
        state: Path,
        node: dict[str, Any],
        launcher: Callable[[dict[str, Any]], ManagedProcess],
        orphan_remover: Callable[[int, str], None],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.node = node
        self.launcher = launcher
        self.orphan_remover = orphan_remover
        self.clock = clock
        self.lock = threading.RLock()
        self.children: dict[str, ManagedProcess] = {}
        state.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(state, check_same_thread=False)
        os.chmod(state, 0o600)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, fingerprint TEXT, "
            "expires INTEGER, port INTEGER, pid INTEGER, revoked INTEGER NOT NULL)"
        )
        self.db.commit()
        # Old native children must be dead before a restarted agent serves requests.
        for (identifier,) in self.db.execute(
            "SELECT id FROM leases WHERE revoked=0 OR pid IS NOT NULL"
        ).fetchall():
            self.remove(UUID(identifier))

    def _cleanup_expired(self) -> None:
        for (identifier,) in self.db.execute(
            "SELECT id FROM leases WHERE revoked=0 AND expires<=?", (int(self.clock()),)
        ).fetchall():
            self.remove(UUID(identifier))

    def issue(self, lease: ManagedLease) -> dict[str, Any]:
        lease.validate(int(self.clock()))
        identifier = str(lease.id)
        fingerprint = hashlib.sha256(
            f"{identifier}:{lease.secret}:{lease.expires}".encode()
        ).hexdigest()
        with self.lock:
            self._cleanup_expired()
            row = self.db.execute(
                "SELECT fingerprint,port,revoked FROM leases WHERE id=?", (identifier,)
            ).fetchone()
            if row:
                child = self.children.get(identifier)
                if row[0] != fingerprint or row[2] or child is None or child.poll() is not None:
                    raise ManagedUnavailable("managed lease unavailable")
                return self._public(row[1])
            used = {r[0] for r in self.db.execute("SELECT port FROM leases WHERE revoked=0")}
            port = next(
                (
                    p
                    for p in range(self.node["port_first"], self.node["port_last"] + 1)
                    if p not in used
                ),
                None,
            )
            if port is None:
                raise ManagedUnavailable("managed capacity unavailable")
            self.db.execute(
                "INSERT INTO leases VALUES (?,?,?,?,NULL,0)",
                (identifier, fingerprint, lease.expires, port),
            )
            self.db.commit()
            try:
                child = self.launcher(
                    {
                        "id": identifier,
                        "secret": lease.secret,
                        "expires": lease.expires,
                        "port": port,
                        "listen": self.node["listen"],
                        "private_key": self.node["private_key"],
                        "server_name": self.node["server_name"],
                        "target": self.node["target"],
                        "short_id": self.node["short_id"],
                    }
                )
                self.children[identifier] = child
                self.db.execute("UPDATE leases SET pid=? WHERE id=?", (child.pid, identifier))
                self.db.commit()
            except Exception:
                self.remove(lease.id)
                raise ManagedUnavailable("managed engine unavailable") from None
            return self._public(port)

    def _public(self, port: int) -> dict[str, Any]:
        return {
            "port": port,
            "public_key": self.node["public_key"],
            "server_name": self.node["server_name"],
            "short_id": self.node["short_id"],
        }

    def remove(self, identifier: UUID) -> None:
        value = str(identifier)
        with self.lock:
            # Commit a tombstone BEFORE signaling: delayed PUT cannot resurrect it.
            self.db.execute(
                "INSERT INTO leases(id,revoked) VALUES (?,1) "
                "ON CONFLICT(id) DO UPDATE SET revoked=1",
                (value,),
            )
            self.db.commit()
            row = self.db.execute("SELECT pid FROM leases WHERE id=?", (value,)).fetchone()
            child = self.children.get(value)
            if child is not None:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=5)
                if child.poll() is None:
                    raise ManagedUnavailable("managed cleanup unconfirmed")
                self.children.pop(value, None)
                if isinstance(child, subprocess.Popen):
                    if child.stdin is not None:
                        child.stdin.close()
                    if child.stdout is not None:
                        child.stdout.close()
            elif row and row[0]:
                self.orphan_remover(row[0], value)
            self.db.execute("UPDATE leases SET pid=NULL WHERE id=?", (value,))
            self.db.commit()


def load_managed_controller(config_path: Path) -> ManagedController:
    config = json.loads(config_path.read_text())
    if set(config) != {
        "listen",
        "private_key",
        "public_key",
        "server_name",
        "target",
        "short_id",
        "port_first",
        "port_last",
    }:
        raise ValueError("invalid managed node configuration")
    if (
        not 1024 <= config["port_first"] <= config["port_last"] <= 65535
        or config["port_last"] - config["port_first"] > 63
    ):
        raise ValueError("invalid managed port range")
    launcher = ProcessLauncher(Path("/usr/local/lib/prettylisavpn/pl-node-engine"))
    return ManagedController(
        Path("/var/lib/prettylisavpn-agent/managed.sqlite3"),
        config,
        launcher,
        launcher.remove_orphan,
    )
