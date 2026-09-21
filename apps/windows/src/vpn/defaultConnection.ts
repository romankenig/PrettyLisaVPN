import type { ApiClient } from "../api/client";
import { createVpnConnectionManager } from "./connection";
import {
  createWireGuardProtocol,
  createWireGuardProvisioner,
} from "./wireguard";

export function createDefaultVpnConnection(api: ApiClient) {
  return createVpnConnectionManager(
    api,
    createWireGuardProvisioner(api),
    createWireGuardProtocol(),
  );
}
