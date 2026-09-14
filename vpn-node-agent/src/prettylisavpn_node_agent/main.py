"""Production mTLS server entry point."""

import ssl

import uvicorn

from prettylisavpn_node_agent.app import create_app
from prettylisavpn_node_agent.config import AgentSettings
from prettylisavpn_node_agent.logging import LOG_CONFIG
from prettylisavpn_node_agent.wireguard import WireGuardController


def main() -> None:
    settings = AgentSettings.from_environment()
    controller = WireGuardController(
        settings.interface,
        settings.client_subnet,
        settings.gateway,
    )
    uvicorn.run(
        create_app(settings, controller),
        host=settings.bind_host,
        port=settings.bind_port,
        access_log=False,
        log_config=LOG_CONFIG,
        log_level="info",
        ssl_certfile=str(settings.tls_certificate),
        ssl_keyfile=str(settings.tls_private_key),
        ssl_ca_certs=str(settings.tls_client_ca),
        ssl_cert_reqs=ssl.CERT_REQUIRED,
        server_header=False,
    )


if __name__ == "__main__":
    main()
