"""Loopback-only UI fixtures. Never connects to production or creates VPN tunnels."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from threading import Thread

USER_ID = "11111111-1111-4111-8111-111111111111"
DEVICE_ID = "22222222-2222-4222-8222-222222222222"
INSTALLATION_ID = "33333333-3333-4333-8333-333333333333"
SESSION_ID = "44444444-4444-4444-8444-444444444444"
DATE = "2026-10-16T00:00:00Z"


def fixture(method, path, body):
    if method == "POST" and path == "/auth/request-otp":
        return 200, {"status": "accepted"}
    if method == "POST" and path == "/auth/verify-otp":
        return 200, {
            "token_type": "bearer",
            "access_token": "ui-review-access-not-a-real-token",
            "access_token_expires_in": 3600,
            "refresh_token": "ui-review-refresh-not-a-real-token",
            "refresh_token_expires_at": "2099-01-01T00:00:00Z",
            "session_id": SESSION_ID,
            "user": {"id": USER_ID},
            "device": {
                "id": DEVICE_ID,
                "installation_id": body.get("installation_id", INSTALLATION_ID),
                "status": "ACTIVE",
            },
            "subscription": {"plan": "PREMIUM", "status": "ACTIVE"},
        }
    if method == "GET" and path == "/public-location":
        return 200, {"success": True, "ip": "203.0.113.42", "country_code": "RU", "city": "Москва"}
    if method == "GET" and path == "/me":
        return 200, {
            "id": USER_ID, "email": "ui-review@example.com",
            "plan": "PREMIUM", "active_device_count": 2,
        }
    if method == "GET" and path == "/devices":
        return 200, [
            {
                "id": device_id, "installation_id": INSTALLATION_ID,
                "device_name": name, "platform": platform,
                "status": "ACTIVE", "created_at": DATE, "updated_at": DATE,
                "revoked_at": None, "is_current": current,
            }
            for device_id, name, platform, current in [
                (DEVICE_ID, "Windows device", "WINDOWS", True),
                ("55555555-5555-4555-8555-555555555555", "Android phone", "ANDROID", False),
            ]
        ]
    if method == "GET" and path == "/vpn/countries":
        return 200, {
            "autopilot": {"quality": 95, "available": True},
            "countries": [
                {"country_code": "DE", "quality": 90, "available": True},
                {"country_code": "US", "quality": 75, "available": True},
                {"country_code": "NL", "quality": 93, "available": True},
                {"country_code": "FR", "quality": 84, "available": True},
            ],
        }
    if method == "GET" and path == "/vpn/sessions/current":
        return 200, {"session": None}
    if method == "POST" and path == "/auth/logout":
        return 200, {"status": "logged_out"}
    # Fail closed: no VPN session creation or device mutation.
    return 404, {"error": {"code": "HTTP_ERROR"}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length)) if length else {}
        status, data = fixture(self.command, self.path, body)
        encoded = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = respond
    do_POST = respond
    do_DELETE = respond


def self_test():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:" + str(server.server_port)
    try:
        with urlopen(base + "/me", timeout=2) as response:
            assert json.load(response)["email"] == "ui-review@example.com"
        request = Request(
            base + "/auth/verify-otp",
            data=json.dumps({"installation_id": INSTALLATION_ID}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=2) as response:
            assert json.load(response)["device"]["installation_id"] == INSTALLATION_ID
        assert fixture("POST", "/vpn/sessions", {})[0] == 404
        assert fixture("DELETE", "/devices/" + DEVICE_ID, {})[0] == 404
        assert fixture("GET", "/vpn/sessions/current", {}) == (200, {"session": None})
        print("Loopback fixture checks passed")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
