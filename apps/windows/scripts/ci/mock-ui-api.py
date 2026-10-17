"""Loopback-only UI fixtures. Never connects to production or creates VPN tunnels."""
import argparse
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from threading import Thread

USER_ID = "11111111-1111-4111-8111-111111111111"
DEVICE_ID = "22222222-2222-4222-8222-222222222222"
INSTALLATION_ID = "33333333-3333-4333-8333-333333333333"
SESSION_ID = "44444444-4444-4444-8444-444444444444"
DATE = "2026-10-16T00:00:00Z"
BILLING_FIXTURES = json.loads(Path(__file__).with_name("billing-fixtures.json").read_text(encoding="utf-8"))
BILLING_SCENARIO = "active"
BILLING_OPERATION = None
BILLING_LAST_COMMAND = None
BILLING_REQUESTS = {}
SIMULATE_VPN = False
DEMO_SESSION = None
DEMO_VPN_ID = "66666666-6666-4666-8666-666666666666"
DEMO_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def fixture(method, path, body):
    global DEMO_SESSION, BILLING_SCENARIO, BILLING_OPERATION, BILLING_LAST_COMMAND
    if SIMULATE_VPN and method == "POST" and path == "/ui-review/billing-scenario":
        scenario = body.get("scenario")
        if scenario not in (*BILLING_FIXTURES, "error"):
            return 400, {"error": {"code": "INVALID_SCENARIO"}}
        BILLING_SCENARIO = scenario
        BILLING_OPERATION = None
        BILLING_LAST_COMMAND = None
        BILLING_REQUESTS.clear()
        return 200, {"status": "ok"}
    if SIMULATE_VPN and method == "POST" and path == "/ui-review/billing-confirm":
        if BILLING_OPERATION:
            BILLING_OPERATION["status"] = "SUCCEEDED"
            BILLING_OPERATION["redirect_url"] = None
            BILLING_SCENARIO = "active"
        return 200, {"status": "ok"}
    if SIMULATE_VPN and method == "GET" and path == "/ui-review/billing-last-command":
        return 200, BILLING_LAST_COMMAND
    if method == "GET" and path == "/billing/overview":
        if BILLING_SCENARIO == "error":
            return 503, {"error": {"code": "BILLING_UNAVAILABLE"}}
        return 200, {**BILLING_FIXTURES[BILLING_SCENARIO], "pending_operation_id": BILLING_OPERATION["id"] if BILLING_OPERATION and BILLING_OPERATION["status"] == "PENDING" else None}
    if SIMULATE_VPN and method == "POST" and path == "/billing/operations":
        request_id = body.get("request_id")
        if request_id in BILLING_REQUESTS:
            return 200, BILLING_REQUESTS[request_id]
        if BILLING_SCENARIO == "error":
            return 503, {"error": {"code": "BILLING_UNAVAILABLE"}}
        overview = BILLING_FIXTURES[BILLING_SCENARIO]
        if body.get("expected_revision") != overview["revision"] or body.get("action") not in overview["actions"]:
            return 409, {"error": {"code": "BILLING_CONFLICT"}}
        if body.get("action") in ("SUBSCRIBE", "RENEW") and body.get("payment_route") not in ("MIR", "BANK_CARD", "ALIPAY_WECHAT", "CRYPTO"):
            return 400, {"error": {"code": "PAYMENT_ROUTE_REQUIRED"}}
        BILLING_LAST_COMMAND = body.copy()
        BILLING_OPERATION = {
            "id": "billing-review-operation", "status": "PENDING",
            "redirect_url": None if body["action"] == "CANCEL" else "https://payments.example.test/confirm",
        }
        if body["action"] == "CANCEL":
            BILLING_SCENARIO = "canceled"
            BILLING_OPERATION["status"] = "SUCCEEDED"
        BILLING_REQUESTS[request_id] = BILLING_OPERATION
        return 200, BILLING_OPERATION
    if method == "GET" and path == "/billing/operations/billing-review-operation" and BILLING_OPERATION:
        return 200, BILLING_OPERATION
    if SIMULATE_VPN and method == "POST" and path == "/vpn/sessions":
        DEMO_SESSION = {
            "session_id": DEMO_VPN_ID, "status": "ACTIVE", "country_code": "DE",
            "expires_at": None, "server_time": DATE,
            "transport": {"endpoint": {"ipv4": "192.0.2.20", "port": 51820},
                          "server_public_key": DEMO_KEY, "client_address": "10.77.0.2/32",
                          "dns": ["1.1.1.1"], "allowed_ips": ["0.0.0.0/0"]},
        }
        return 200, DEMO_SESSION
    if SIMULATE_VPN and method == "DELETE" and path == "/vpn/sessions/" + DEMO_VPN_ID:
        DEMO_SESSION = None
        return 200, {"session_id": DEMO_VPN_ID, "status": "DISCONNECTED"}
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
        if SIMULATE_VPN and DEMO_SESSION:
            return 200, {"success": True, "ip": "198.51.100.42", "country_code": "DE", "city": "Berlin"}
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
                # Synthetic future-contract field; the other device has no login data.
                "last_login_at": "2026-10-17T09:30:00Z" if current else None,
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
        return 200, {"session": DEMO_SESSION if SIMULATE_VPN else None}
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
    parser.add_argument("--simulate-vpn", action="store_true", help="Synthetic session data only; requires mocked native IPC")
    args = parser.parse_args()
    SIMULATE_VPN = args.simulate_vpn
    if args.self_test:
        self_test()
    else:
        ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
