import type { ApiClient } from "../api/client";
import { createVpnConnectionManager } from "./connection";
import { createWireGuardProvisioner } from "./wireguard";
import { createAutomaticProtocol } from "./profileAdapter";

export function createDefaultVpnConnection(api: ApiClient) {
  return createVpnConnectionManager(
    api,
    createWireGuardProvisioner(api),
    createAutomaticProtocol(),
  );
}
