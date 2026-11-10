// Test-only adapters exercise the real executor without starting a VPN.
import { createVpnConnectionManager } from "../vpn/connection";
import { placeholderAdapters } from "./placeholders";
export const createReviewVpnConnection = () =>
  createVpnConnectionManager(
    placeholderAdapters().map((adapter) => ({
      ...adapter,
      async connect(selection, signal) {
        const data = document.documentElement.dataset;
        if (data.vpnReviewConnect !== "1")
          return adapter.connect(selection, signal);
        data.vpnReviewAttempts = [data.vpnReviewAttempts, adapter.id]
          .filter(Boolean)
          .join(",");
        if (adapter.id !== "amneziawg") return { connected: false };
        return {
          connected: true,
          internetVerified: true,
          details: {
            protocol: "AmneziaWG",
            transport: "synthetic",
            server: "fixture",
            encryption: "synthetic",
            obfuscation: "synthetic",
          },
        };
      },
    })),
  );
