"""WireGuard lifecycle adapter. All private keys stay on their Ubuntu nodes."""

from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Interface
from uuid import UUID

from prettylisavpn.fleet.domain import (
    Access,
    FleetError,
    MethodState,
    Node,
    Observation,
    RelayAccess,
    VpnMethod,
    WireGuardConfig,
)
from prettylisavpn.fleet.ssh import NodeTransport


class WireGuardMethod(VpnMethod):
    name = "wireguard"

    def __init__(self, transport: NodeTransport) -> None:
        self.transport = transport

    async def inspect(self, node: Node) -> MethodState:
        return MethodState.model_validate(await self.transport.call(node, "inspect"))

    async def plan(self, node: Node, config: dict[str, object]) -> dict[str, object]:
        parsed = WireGuardConfig.model_validate(config)
        return {
            "method": self.name,
            "os": "ubuntu",
            "interface": "pl-wg0",
            "configuration": parsed.model_dump(mode="json"),
            "private_keys": "node_only",
        }

    async def configure(
        self, node: Node, config: dict[str, object], operation_id: UUID
    ) -> MethodState:
        parsed = WireGuardConfig.model_validate(config)
        await self.transport.bootstrap(node)
        try:
            result = await self.transport.call(
                node,
                "configure",
                {
                    "configuration": parsed.model_dump(mode="json"),
                    "host": node.host,
                    "operation_id": str(operation_id),
                },
                command_timeout=120,
            )
        except FleetError:
            await self.rollback(node, operation_id)
            raise
        return MethodState.model_validate(result)

    async def grant_access(self, node: Node, access: Access) -> None:
        await self.transport.call(node, "grant", {"access": access.model_dump(mode="json")})

    async def revoke_access(self, node: Node, access: Access) -> bool:
        result = await self.transport.call(
            node, "revoke", {"access_id": str(access.id), "purpose": access.purpose}
        )
        return result.get("removed") is True

    async def grant_relay(self, node: Node, access: RelayAccess) -> None:
        if node.group != "INTERMEDIATE":
            raise FleetError("RELAY_GROUP_INVALID")
        result = await self.transport.call(
            node, "grant-relay", {"access": access.model_dump(mode="json")}
        )
        if result.get("granted") is not True:
            raise FleetError("RELAY_GRANT_UNCONFIRMED")

    async def revoke_relay(self, node: Node, access: RelayAccess) -> bool:
        result = await self.transport.call(node, "revoke-relay", {"access_id": str(access.id)})
        return result.get("removed") is True

    async def observe(self, node: Node) -> Observation:
        return Observation.model_validate(await self.transport.call(node, "observe"))

    async def rollback(self, node: Node, operation_id: UUID) -> None:
        await self.transport.call(node, "rollback", {"operation_id": str(operation_id)})

    async def probe(self, source: Node, target: Node, check_id: UUID) -> Observation:
        # The reserved monitoring address is independent of all customer peers.
        state = await self.inspect(target)
        if not state.public_key or not state.configuration:
            raise FleetError("TARGET_CONFIGURATION_MISSING")
        access: Access | None = None
        result: Observation | None = None
        cleanup = True
        try:
            preparation = await self.transport.call(
                source, "prepare", {"check_id": str(check_id)}, command_timeout=45
            )
            subnet = IPv4Interface(str(state.configuration["address"]))
            access = Access(
                id=check_id,
                public_key=preparation["public_key"],
                address=str(subnet.network.broadcast_address - 1) + "/32",
                expires_at=datetime.now(UTC) + timedelta(minutes=4),
            )
            await self.grant_access(target, access)
            response = await self.transport.call(
                source,
                "probe",
                {
                    "check_id": str(check_id),
                    "public_key": state.public_key,
                    "endpoint": target.host,
                    "listen_port": state.configuration["listen_port"],
                    "address": access.address,
                    "mtu": state.configuration["mtu"],
                    "expected_egress_ips": target.expected_egress_ips,
                },
                command_timeout=150,
            )
            result = Observation.model_validate(response)
        except FleetError as exc:
            result = Observation(
                status="UNKNOWN", mode="CONTROL", code=exc.code, observed_at=datetime.now(UTC)
            )
        finally:
            if access is not None:
                try:
                    cleanup = await self.revoke_access(target, access)
                except FleetError:
                    cleanup = False
            try:
                cleanup = (
                    await self.transport.call(source, "dispose", {"check_id": str(check_id)})
                ).get("removed") is True and cleanup
            except FleetError:
                cleanup = False
        assert result is not None
        if not cleanup:
            return Observation(
                status="UNKNOWN",
                mode="CONTROL",
                code="CLEANUP_UNCONFIRMED",
                observed_at=datetime.now(UTC),
                cleanup_confirmed=False,
            )
        # Include customer load in the same sample as the end-to-end result.
        # inspect/counts excludes the monitoring peer, so the probe cannot lower
        # its own score or consume a customer admission slot.
        return result.model_copy(
            update={
                "active_connections": state.active_connections,
                "authorized_connections": state.authorized_connections,
            }
        )
