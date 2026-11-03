from html.parser import HTMLParser
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from prettylisavpn.config import Settings
from prettylisavpn.main import create_app


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.hrefs.append(dict(attrs).get("href"))


@pytest.mark.parametrize("path", ["/support", "/support/"])
def test_public_contact_page_opens_only_the_fixed_support_mailbox(path):
    app = create_app(Settings(_env_file=None, environment="test"))
    app.state.support = AsyncMock()
    client = TestClient(app)
    response = client.get(
        path, params={"email": "private@example.invalid", "next": "https://evil.invalid"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "PrettyLisaVPN" in response.text
    assert "private@example.invalid" not in response.text
    assert "evil.invalid" not in response.text
    assert "<form" not in response.text and "<script" not in response.text
    links = Links()
    links.feed(response.text)
    assert links.hrefs == ["mailto:help@prettylisavpn.com"]
    app.state.support.accept.assert_not_called()
    assert client.post(path).status_code == 405


@pytest.mark.parametrize("page", ["success", "failure"])
def test_payment_return_pages_link_to_the_public_support_page(page):
    client = TestClient(create_app(Settings(_env_file=None, environment="test")))
    links = Links()
    links.feed(client.get(f"/payment/{page}").text)
    assert "/support" in links.hrefs
