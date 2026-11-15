"""Managed encrypted protocols behind the existing fleet lifecycle and SSH port."""

import base64
import secrets
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address
from uuid import UUID

from pydantic import SecretStr

from prettylisavpn.client_vpn.methods import MANAGED_METHODS, base_method, lease_credential, profile
from prettylisavpn.fleet.domain import (
    Access,
    FleetError,
    ManagedAccess,
    ManagedConfig,
    MethodState,
    Node,
    Observation,
    RelayAccess,
    VpnMethod,
)
from prettylisavpn.fleet.ssh import NodeTransport
from prettylisavpn.fleet.wireguard import WireGuardMethod


class ManagedVpnMethod(VpnMethod):
    name = "managed"

    def __init__(self, transport: NodeTransport, key: SecretStr | None) -> None:
        self.transport, self.key = transport, key
        self.relay = WireGuardMethod(transport)

    async def inspect(self, node: Node) -> MethodState:
        return MethodState.model_validate(await self.transport.call(node, "managed-inspect"))

    async def plan(self, node: Node, config: dict[str, object]) -> dict[str, object]:
        parsed = ManagedConfig.model_validate(config)
        return {
            "method": self.name,
            "os": "ubuntu",
            "configuration": parsed.model_dump(mode="json"),
            "private_keys": "node_only",
            "methods": list(MANAGED_METHODS),
        }

    async def configure(
        self, node: Node, config: dict[str, object], operation_id: UUID
    ) -> MethodState:
        parsed = ManagedConfig.model_validate(config)
        await self.transport.bootstrap(node)
        return MethodState.model_validate(
            await self.transport.call(
                node,
                "managed-configure",
                {
                    "host": node.host,
                    "configuration": parsed.model_dump(mode="json"),
                },
            )
        )

    async def grant_access(self, node: Node, access: Access) -> None:
        if not isinstance(access, ManagedAccess):
            raise FleetError("VPN_METHOD_UNSUPPORTED", 422)
        engine = (
            "HTTPS_PROXY"
            if access.method == "https_proxy"
            else MANAGED_METHODS[base_method(access.method)].engine
        )
        response = await self.transport.call(
            node,
            "managed-grant",
            {
                "access": {
                    "id": str(access.id),
                    "purpose": access.purpose,
                    "method": engine,
                    "port": access.listen_port,
                    "secret": lease_credential(self.key, access.id, node.id).get_secret_value(),
                    "expires_at": access.expires_at.isoformat(),
                }
            },
        )
        if response.get("granted") is not True:
            raise FleetError("MANAGED_GRANT_UNCONFIRMED")

    async def revoke_access(self, node: Node, access: Access) -> bool:
        response = await self.transport.call(node, "managed-revoke", {"access_id": str(access.id)})
        return response.get("removed") is True

    async def grant_relay(self, node: Node, access: RelayAccess) -> None:
        await self.relay.grant_relay(node, access)

    async def revoke_relay(self, node: Node, access: RelayAccess) -> bool:
        return await self.relay.revoke_relay(node, access)

    async def observe(self, node: Node) -> Observation:
        return Observation(
            status="UNKNOWN",
            mode="CONTROL",
            code="MANAGED_PROBE_REQUIRED",
            observed_at=datetime.now(UTC),
        )

    async def rollback(self, node: Node, operation_id: UUID) -> None:
        # Configuration only installs shared tooling and node-owned identity.
        # Never tear down another lease or WireGuard during a configure retry.
        return None

    async def probe(
        self,
        source: Node,
        target: Node,
        check_id: UUID,
        service_url: str | None = None,
        service_domains: list[str] | None = None,
        selected_method: str | None = None,
        *,
        relay: Node | None = None,
        relay_port: int | None = None,
    ) -> Observation:
        state = await self.inspect(target)
        if not state.installed or not state.public_key:
            raise FleetError("TARGET_CONFIGURATION_MISSING")
        now = datetime.now(UTC)
        names = tuple(MANAGED_METHODS)
        method = (
            selected_method or names[(int(now.timestamp()) // 3600 + target.id.int) % len(names)]
        )
        native = base_method(method)
        if native not in (*names, "https_proxy") or method.endswith("_relay") != (
            relay is not None
        ):
            raise FleetError("VPN_METHOD_UNSUPPORTED")
        access = ManagedAccess(
            purpose="monitor",
            id=check_id,
            public_key=base64.b64encode(secrets.token_bytes(32)).decode(),
            address="",
            expires_at=now + timedelta(seconds=170),
            method=method,
            listen_port=49900 + check_id.int % 100,
        )
        result: Observation
        cleanup = False
        forwarding: RelayAccess | None = None
        try:
            await self.grant_access(target, access)
            if relay is not None:
                if relay_port is None or relay.id in (source.id, target.id):
                    raise FleetError("RELAY_PROBE_ROUTE_INVALID")
                forwarding = RelayAccess(
                    id=check_id,
                    listen_port=relay_port,
                    target_host=IPv4Address(target.host),
                    target_port=access.listen_port,
                    protocol=MANAGED_METHODS[native].network,
                    expires_at=access.expires_at,
                )
                await self.grant_relay(relay, forwarding)
            probe_profile = (
                {
                    "method": "HTTPS_PROXY",
                    "server": state.configuration["proxy_host"],
                    "port": access.listen_port,
                    "username": str(check_id),
                    "secret": lease_credential(self.key, check_id, target.id).get_secret_value(),
                }
                if native == "https_proxy"
                else profile(
                    method=method,
                    lease_id=check_id,
                    node_id=target.id,
                    key=self.key,
                    host=relay.host if relay else target.host,
                    port=relay_port if relay_port is not None else access.listen_port,
                    country=target.country_code,
                    public_key=state.public_key,
                    configuration=state.configuration,
                )
            )
            response = await self.transport.call(
                source,
                "managed-probe",
                {
                    "profile": probe_profile,
                    "expected_egress_ips": target.expected_egress_ips,
                    **(
                        {"service_url": service_url, "service_domains": service_domains}
                        if service_url
                        else {}
                    ),
                },
                command_timeout=90,
            )
            result = Observation.model_validate(response)
        except FleetError as error:
            result = Observation(
                status="UNKNOWN", mode="CONTROL", code=error.code, observed_at=datetime.now(UTC)
            )
        finally:
            try:
                cleanup = await self.revoke_access(target, access)
            except FleetError:
                cleanup = False
            if relay is not None and forwarding is not None:
                try:
                    cleanup = await self.revoke_relay(relay, forwarding) and cleanup
                except FleetError:
                    cleanup = False
        if not cleanup:
            return Observation(
                status="UNKNOWN",
                mode="CONTROL",
                code="CLEANUP_UNCONFIRMED",
                observed_at=datetime.now(UTC),
                cleanup_confirmed=False,
            )
        return result.model_copy(
            update={
                "active_connections": state.active_connections,
                "authorized_connections": state.authorized_connections,
            }
        )
