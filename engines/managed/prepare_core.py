"""Reproduce the narrowly patched MPL core without changing the shared Go cache."""

import argparse
import hashlib
import json
import shutil
import stat
import subprocess
from pathlib import Path

MODULE = "github.com/xtls/xray-core"
VERSION = "v1.260327.1-0.20261021115930-1b1647cd9ddf"
SUM = "h1:Eqz6sj4Up2NtymyVY2UtXNpHZqJGrMwKsXnGOySyUNI="
FILE = Path("transport/internet/hysteria/conn.go")
ORIGINAL = "d14c8699bc3c749ee0d186faebc0c8ae1fe56813854bfefc2c4d777fb6258c72"
MARKER = ".prettylisa-patch.json"
GRPC_FILES = {
    "transport/internet/grpc/encoding/hunkconn.go": (
        "819e20f5d2ba14e3636adcf81f4fa78ccce702f298c3c785b803fce803aa3d3f"
    ),
    "transport/internet/grpc/encoding/multiconn.go": (
        "df50cffe73d7fe510a766ce953f72c2bd39deebc83faef3334a641529af9a2b9"
    ),
    "transport/internet/grpc/dial.go": (
        "f429ec9bb1fa143bc9c42cbcd976a20ef17774e37403444d0232d621d5de439d"
    ),
}


def grpc_patched(path: str, source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != GRPC_FILES[path]:
        raise ValueError("Pinned gRPC source changed; review the patch")
    text = source.decode("utf-8")
    if path.endswith("/dial.go"):
        text = text.replace(
            "client := encoding.NewGRPCServiceClient(conn)",
            "ctx, cancel := context.WithCancel(ctx)\n\t"
            "client := encoding.NewGRPCServiceClient(conn)",
        )
        text = text.replace("grpcService, nil, nil", "grpcService, cancel, nil")
        # Cancel only stream-creation errors, after the child context exists.
        before, after = text.split("ctx, cancel := context.WithCancel(ctx)", 1)
        after = after.replace(
            'return nil, errors.New("Cannot dial gRPC").Base(err)',
            'cancel()\n\t\treturn nil, errors.New("Cannot dial gRPC").Base(err)',
        )
        text = before + "ctx, cancel := context.WithCancel(ctx)" + after
    else:
        kind = "MultiHunkReaderWriter" if path.endswith("/multiconn.go") else "HunkReaderWriter"
        text = text.replace('"io"', '"io"\n\t"sync"')
        text = text.replace("done   *done.Instance", "done   *done.Instance\n\twriteMu sync.Mutex")
        old = "hc, cancel, done.New(), nil" + ("" if kind.startswith("Multi") else ", 0")
        text = text.replace("{" + old + "}", "{hc: hc, cancel: cancel, done: done.New()}")
        signature = (
            "WriteMultiBuffer(mb buf.MultiBuffer) error"
            if kind.startswith("Multi")
            else "Write(buf []byte) (int, error)"
        )
        text = text.replace(
            f"func (h *{kind}) {signature} {{",
            f"func (h *{kind}) {signature} {{\n\th.writeMu.Lock()\n\tdefer h.writeMu.Unlock()",
        )
        text = text.replace(
            f"func (h *{kind}) Close() error {{",
            f"func (h *{kind}) Close() error {{\n\t_ = h.done.Close()",
        )
        text = text.replace(
            "if sc, match := h.hc.(StreamCloser); match {",
            "h.writeMu.Lock()\n\tdefer h.writeMu.Unlock()\n\t"
            "if sc, match := h.hc.(StreamCloser); match {",
        )
    return (
        "// SPDX-License-Identifier: MPL-2.0\n"
        "// PrettyLisaVPN modification: cancel blocked sends before serialized stream shutdown.\n"
        + text
    ).encode()


def patched(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != ORIGINAL:
        raise ValueError("Pinned Hysteria source changed; review the patch")
    text = source.decode("utf-8")
    for old, new, count in (
        ('"sync"', '"sync"\n\t"sync/atomic"', 1),
        ("closed bool", "closed atomic.Bool", 2),
        ("if c.closed {", "if c.closed.Load() {", 1),
        (
            "if !udpConn.closed {\n\t\tudpConn.closed = true",
            "if udpConn.closed.CompareAndSwap(false, true) {",
            1,
        ),
        ("if m.closed {", "if m.closed.Load() {", 2),
        ("m.closed = true", "m.closed.Store(true)", 1),
    ):
        if text.count(old) != count:
            raise ValueError("Unexpected Hysteria synchronization layout")
        text = text.replace(old, new)
    return (
        "// SPDX-License-Identifier: MPL-2.0\n"
        "// PrettyLisaVPN modification: atomic UDP/session closed flags.\n" + text
    ).encode()


def prepare(go: str) -> None:
    root = Path(__file__).resolve().parent
    info = json.loads(
        subprocess.check_output([go, "mod", "download", "-json", MODULE + "@" + VERSION], cwd=root)
    )
    if info.get("Sum") != SUM or info.get("Version") != VERSION:
        raise ValueError("Pinned core checksum mismatch")
    origin = Path(info["Dir"])
    changes = {FILE: patched((origin / FILE).read_bytes())}
    changes.update(
        {Path(path): grpc_patched(path, (origin / path).read_bytes()) for path in GRPC_FILES}
    )
    target = root / "patched" / "xray-core"
    if target.resolve().parent != (root / "patched").resolve() or target.is_symlink():
        raise ValueError("Unexpected generated source location")
    expected = {file.relative_to(origin) for file in origin.rglob("*") if file.is_file()}
    if target.exists():
        if not (target / MARKER).is_file():
            raise ValueError("Refusing to overwrite an unknown directory")
        actual = {file.relative_to(target) for file in target.rglob("*") if file.is_file()}
        if actual - expected - {Path(MARKER)} or any(
            file.is_symlink() for file in target.rglob("*")
        ):
            raise ValueError("Unexpected files in generated source directory")
    shutil.copytree(origin, target, copy_function=shutil.copyfile, dirs_exist_ok=True)
    # Go's module cache directories are read-only on Unix. copytree preserves
    # directory modes even with copyfile, so make only our verified private copy
    # writable before creating the patch marker (never chmod the shared cache).
    for directory in [target, *(path for path in target.rglob("*") if path.is_dir())]:
        directory.chmod(directory.stat().st_mode | stat.S_IRWXU)
    for filename, content in changes.items():
        (target / filename).write_bytes(content)
    gofmt = (
        str(Path(go).with_name("gofmt.exe" if go.endswith(".exe") else "gofmt"))
        if Path(go).parent != Path(".")
        else "gofmt"
    )
    subprocess.run([gofmt, "-w", *(str(target / filename) for filename in changes)], check=True)
    (target / MARKER).write_text(
        json.dumps(
            {
                "module": MODULE,
                "version": VERSION,
                "sum": SUM,
                "files": {
                    filename.as_posix(): hashlib.sha256(
                        (target / filename).read_bytes()
                    ).hexdigest()
                    for filename in changes
                },
            }
        ),
        encoding="utf-8",
    )
    print("Pinned MPL core prepared with Hysteria and gRPC shutdown fixes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--go", default="go")
    prepare(parser.parse_args().go)
