"""Managed encrypted protocols behind the existing fleet lifecycle and SSH port."""

import base64
import secrets
from datetime import UTC, datetime, timedelta
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
        method = MANAGED_METHODS[base_method(access.method)]
        response = await self.transport.call(
            node,
            "managed-grant",
            {
                "access": {
                    "id": str(access.id),
                    "purpose": access.purpose,
                    "method": method.engine,
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

    async def probe(self, source: Node, target: Node, check_id: UUID) -> Observation:
        state = await self.inspect(target)
        if not state.installed or not state.public_key:
            raise FleetError("TARGET_CONFIGURATION_MISSING")
        now = datetime.now(UTC)
        names = tuple(MANAGED_METHODS)
        method = names[(int(now.timestamp()) // 3600 + target.id.int) % len(names)]
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
        try:
            await self.grant_access(target, access)
            response = await self.transport.call(
                source,
                "managed-probe",
                {
                    "profile": profile(
                        method=method,
                        lease_id=check_id,
                        node_id=target.id,
                        key=self.key,
                        host=target.host,
                        port=access.listen_port,
                        country=target.country_code,
                        public_key=state.public_key,
                        configuration=state.configuration,
                    ),
                    "expected_egress_ips": target.expected_egress_ips,
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
