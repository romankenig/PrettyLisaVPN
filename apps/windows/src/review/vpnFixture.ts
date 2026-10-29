// Test-only failed adapters exercise the real executor without starting a VPN.
import { createVpnConnectionManager } from "../vpn/connection";
import { placeholderAdapters } from "./placeholders";
export const createReviewVpnConnection = () =>
  createVpnConnectionManager(placeholderAdapters());
