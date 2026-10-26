"""Loopback-only UI fixtures. Never connects to production or creates VPN tunnels."""
import argparse
from email.parser import BytesParser
from email.policy import default
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from threading import Thread

USER_ID = "11111111-1111-4111-8111-111111111111"
DEVICE_ID = "22222222-2222-4222-8222-222222222222"
INSTALLATION_ID = "33333333-3333-4333-8333-333333333333"
EVIDENCE_PATH = os.getenv("DEVICE_BACKEND_EVIDENCE_PATH")
DEVICE_EVIDENCE = json.loads(Path(EVIDENCE_PATH).read_text(encoding="utf-8")) if EVIDENCE_PATH else None
BILLING_EVIDENCE_PATH = os.getenv("BILLING_BACKEND_EVIDENCE_PATH")
BILLING_EVIDENCE = json.loads(Path(BILLING_EVIDENCE_PATH).read_text(encoding="utf-8")) if BILLING_EVIDENCE_PATH else None
BILLING_READONLY_OPERATION_ATTEMPTS = 0
DEVICE_REVOKED = False
SUPPORT_REQUESTS = {}
SUPPORT_ATTEMPTS = 0
SUPPORT_DROP_FIRST = True
ACCOUNT_EMAIL = DEVICE_EVIDENCE["account_email"] if DEVICE_EVIDENCE else "ui-review@example.com"
if DEVICE_EVIDENCE:
    current = next(item for item in DEVICE_EVIDENCE["devices"] if item["is_current"])
    USER_ID = DEVICE_EVIDENCE["user_id"]
    DEVICE_ID = current["id"]
    INSTALLATION_ID = current["installation_id"]
SESSION_ID = "44444444-4444-4444-8444-444444444444"
DATE = "2026-10-16T00:00:00Z"
BILLING_FIXTURES = json.loads(Path(__file__).with_name("billing-fixtures.json").read_text(encoding="utf-8"))
BILLING_SCENARIO = "active"
BILLING_OPERATION = None
BILLING_LAST_COMMAND = None
BILLING_REQUESTS = {}
SIMULATE_BILLING = False
SIMULATE_MESSAGES = False
MESSAGE_RECEIPTS = set()
MESSAGE_ACK_ATTEMPTS = 0
MESSAGE_FIXTURES = [
    {
        "id": "88888888-8888-4888-8888-888888888888", "revision": 1,
        "kind": "update", "title": "стало удобнее",
        "blocks": [
            {"type": "paragraph", "text": "демонстрационное сообщение из тестового API PrettyLisaVPN."},
            {"type": "list", "items": ["новости и обновления прямо в приложении", "подтверждения синхронизируются через аккаунт"]},
        ],
        "fallback_text": "демонстрационное сообщение из тестового API PrettyLisaVPN.",
        "primary_action": None, "dismiss_label": "понятно", "expires_at": None,
    },
    {
        "id": "99999999-9999-4999-8999-999999999999", "revision": 1,
        "kind": "promotion", "title": "специальное предложение",
        "blocks": [{"type": "paragraph", "text": "здесь появятся условия акции от сервера. это демонстрационный пример, не настоящая акция."}],
        "fallback_text": "демонстрационный пример акции.",
        "primary_action": {"type": "OPEN_SUBSCRIPTION", "label": "посмотреть подписку"},
        "dismiss_label": "понятно", "expires_at": None,
    },
]


def fixture(method, path, body):
    global BILLING_SCENARIO, BILLING_OPERATION, BILLING_LAST_COMMAND
    global MESSAGE_ACK_ATTEMPTS, DEVICE_REVOKED, BILLING_READONLY_OPERATION_ATTEMPTS
    if BILLING_SCENARIO.startswith("server-") and BILLING_EVIDENCE:
        if method == "GET" and urlsplit(path).path == "/billing/overview":
            return 200, BILLING_EVIDENCE["snapshots"][BILLING_SCENARIO.removeprefix("server-")]
        if urlsplit(path).path.startswith("/billing/operations"):
            BILLING_READONLY_OPERATION_ATTEMPTS += 1
            return 404, {"error": {"code": "NOT_FOUND"}}
    if method == "GET" and urlsplit(path).path == "/ui-review/billing-readonly-evidence":
        return 200, {"operation_attempts": BILLING_READONLY_OPERATION_ATTEMPTS}
    path = urlsplit(path).path
    # Replay allowlisted, non-secret responses recorded by the real backend in CI.
    if DEVICE_EVIDENCE:
        if method == "GET" and path == "/version":
            return 200, DEVICE_EVIDENCE["version"]
        if method == "GET" and path == "/devices":
            return 200, DEVICE_EVIDENCE["after_revoke" if DEVICE_REVOKED else "devices"]
        if method == "DELETE" and path == "/devices/" + DEVICE_EVIDENCE["revoked_response"]["device"]["id"]:
            DEVICE_REVOKED = True
            return 200, DEVICE_EVIDENCE["revoked_response"]
    if SIMULATE_MESSAGES and method == "GET" and path == "/messages":
        return 200, {"schema_version": 1, "messages": [item for item in MESSAGE_FIXTURES if (item["id"], item["revision"]) not in MESSAGE_RECEIPTS]}
    if SIMULATE_MESSAGES and method == "POST" and path.startswith("/messages/") and path.endswith("/acknowledgements"):
        message_id = path.split("/")[2]
        if not any(item["id"] == message_id and item["revision"] == body.get("revision") for item in MESSAGE_FIXTURES):
            return 404, {"error": {"code": "MESSAGE_NOT_FOUND"}}
        MESSAGE_ACK_ATTEMPTS += 1
        if MESSAGE_ACK_ATTEMPTS == 1:
            return 503, {"error": {"code": "MESSAGE_ACK_UNAVAILABLE"}}
        MESSAGE_RECEIPTS.add((message_id, body["revision"]))
        return 200, {"id": message_id, "revision": body["revision"], "acknowledged": True}
    if SIMULATE_MESSAGES and method == "GET" and path == "/ui-review/message-receipts":
        return 200, {"acknowledged": len(MESSAGE_RECEIPTS), "attempts": MESSAGE_ACK_ATTEMPTS}
    if SIMULATE_BILLING and method == "POST" and path == "/ui-review/billing-scenario":
        scenario = body.get("scenario")
        if scenario not in (*BILLING_FIXTURES, "error", *(["server-" + key for key in BILLING_EVIDENCE["snapshots"]] if BILLING_EVIDENCE else [])):
            return 400, {"error": {"code": "INVALID_SCENARIO"}}
        BILLING_SCENARIO = scenario
        BILLING_OPERATION = None
        BILLING_LAST_COMMAND = None
        BILLING_REQUESTS.clear()
        return 200, {"status": "ok"}
    if SIMULATE_BILLING and method == "POST" and path == "/ui-review/billing-confirm":
        if BILLING_OPERATION:
            BILLING_OPERATION["status"] = "SUCCEEDED"
            BILLING_OPERATION["redirect_url"] = None
            BILLING_SCENARIO = "active"
        return 200, {"status": "ok"}
    if SIMULATE_BILLING and method == "GET" and path == "/ui-review/billing-last-command":
        return 200, BILLING_LAST_COMMAND
    if method == "GET" and path == "/billing/overview":
        if BILLING_SCENARIO == "error":
            return 503, {"error": {"code": "BILLING_UNAVAILABLE"}}
        return 200, {**BILLING_FIXTURES[BILLING_SCENARIO], "pending_operation_id": BILLING_OPERATION["id"] if BILLING_OPERATION and BILLING_OPERATION["status"] == "PENDING" else None}
    if SIMULATE_BILLING and method == "POST" and path == "/billing/operations":
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
    if method == "POST" and path == "/auth/request-otp":
        return 200, {"status": "accepted"}
    if method == "POST" and path == "/auth/refresh":
        if body.get("session_id") != SESSION_ID or body.get("refresh_token") != "ui-review-refresh-not-a-real-token":
            return 401, {"error": {"code": "AUTH_INVALID"}}
        return 200, {
            "token_type": "bearer",
            "access_token": "ui-review-restored-access-not-a-real-token",
            "access_token_expires_in": 3600,
            "refresh_token": "ui-review-refresh-not-a-real-token",
            "refresh_token_expires_at": "2099-01-01T00:00:00Z",
            "session_id": SESSION_ID,
        }
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
            "id": USER_ID, "email": ACCOUNT_EMAIL,
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
    if method == "POST" and path == "/auth/logout":
        return 200, {"status": "logged_out"}
    # Fail closed: no VPN session creation or device mutation.
    return 404, {"error": {"code": "HTTP_ERROR"}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        content_type = self.headers.get("Content-Type", "")
        if self.path.startswith("/support/requests"):
            global SUPPORT_ATTEMPTS
            request_id = self.path.rsplit("/", 1)[-1]
            if self.command == "POST":
                multipart = BytesParser(policy=default).parsebytes(
                    ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + raw)
                parts = list(multipart.iter_parts())
                report = next(part for part in parts if part.get_param("name", header="content-disposition") == "report")
                payload = json.loads(report.get_payload(decode=True))
                request_id = payload["request_id"]
                SUPPORT_ATTEMPTS += 1
                SUPPORT_REQUESTS.setdefault(request_id, {"request_id": request_id, "status": "ACCEPTED"})
                # Simulate acceptance followed by a lost HTTP response. This fixture sends no email.
                if SUPPORT_DROP_FIRST and SUPPORT_ATTEMPTS == 1:
                    self.connection.shutdown(2)
                    self.connection.close()
                    return
                status, data = 202, SUPPORT_REQUESTS[request_id]
            else:
                data = SUPPORT_REQUESTS.get(request_id)
                status = 200 if data else 404
                data = data or {"error": {"code": "SUPPORT_NOT_FOUND"}}
                if status == 200:
                    data = {**data, "status": "SENT"}
        elif self.path == "/ui-review/support-evidence":
            status, data = 200, {"requests": len(SUPPORT_REQUESTS), "post_attempts": SUPPORT_ATTEMPTS, "email_delivery_tested": False}
        else:
            body = json.loads(raw) if raw else {}
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
            assert json.load(response)["email"] == ACCOUNT_EMAIL
        request = Request(
            base + "/auth/verify-otp",
            data=json.dumps({"installation_id": INSTALLATION_ID}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=2) as response:
            assert json.load(response)["device"]["installation_id"] == INSTALLATION_ID
        refresh_body = {"session_id": SESSION_ID, "refresh_token": "ui-review-refresh-not-a-real-token"}
        request = Request(
            base + "/auth/refresh",
            data=json.dumps(refresh_body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=2) as response:
            assert json.load(response)["session_id"] == SESSION_ID
        assert fixture("POST", "/auth/refresh", {})[0] == 401
        assert fixture("POST", "/vpn/sessions", {})[0] == 404
        assert fixture("DELETE", "/devices/" + DEVICE_ID, {})[0] == 404
        assert fixture("GET", "/vpn/sessions/current", {})[0] == 404
        print("Loopback fixture checks passed")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--simulate-billing", action="store_true", help="Synthetic payment operations only; never charges money")
    parser.add_argument("--simulate-messages", action="store_true", help="Synthetic announcements and account receipts; never a real backend")
    args = parser.parse_args()
    SIMULATE_BILLING = args.simulate_billing
    SIMULATE_MESSAGES = args.simulate_messages
    if args.self_test:
        self_test()
    else:
        ThreadingHTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
