"""Native listener shutdown, without creating a VPN or sending browsing traffic."""

import base64
import json
import os
import select
import socket
import subprocess
import sys
import time
import uuid


def check_shutdown(binary, reason):
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    identifier = str(uuid.uuid4())
    lease = dict(id=identifier, secret=str(uuid.uuid4()), listen="127.0.0.1", port=port,
                 private_key=base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="),
                 server_name="example.com", target="1.1.1.1", short_id="ab",
                 expires=int(time.time()) + (3 if reason in ("expiry", "renewal") else 60))
    child = subprocess.Popen([binary, "--lease", identifier], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        child.stdin.write(json.dumps(lease).encode() + b"\n")
        child.stdin.flush()
        assert select.select([child.stdout], [], [], 5)[0], "native startup timed out"
        assert child.stdout.readline(32) == b"READY\n", "native startup failed"
        with socket.create_connection(("127.0.0.1", port), timeout=2) as connection:
            if reason == "eof":
                child.stdin.close()
            elif reason == "revoke":
                child.kill()
            elif reason == "renewal":
                child.stdin.write(json.dumps({"expires": int(time.time()) + 8}).encode() + b"\n")
                child.stdin.flush()
                time.sleep(4)
                assert child.poll() is None, "renewed lease stopped at the old deadline"
                child.stdin.close()
            elif reason == "invalid-renewal":
                child.stdin.write(json.dumps({"expires": int(time.time()) + 3600}).encode() + b"\n")
                child.stdin.flush()
            child.wait(timeout=6)
            try:
                assert connection.recv(1) == b"", "accepted socket survived process exit"
            except ConnectionResetError:
                pass
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "listener survived process exit"
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        child.stdin.close()
        child.stdout.close()


for condition in ("eof", "expiry", "revoke", "renewal", "invalid-renewal"):
    check_shutdown(sys.argv[1], condition)
    print(f"Native listener and accepted socket closed: {condition}")
