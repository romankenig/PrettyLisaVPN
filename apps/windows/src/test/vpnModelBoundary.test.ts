import { describe, expect, it } from "vitest";
import type {
  AutopilotAvailability,
  CountryAvailability,
  CountryDiscoveryModel,
} from "../vpn/discovery";
import type { WireGuardTransportConfiguration } from "../native/wireguardTransport";

type ForbiddenDiscoveryKey =
  | "nodeId"
  | "nodeName"
  | "nodeCount"
  | "provider"
  | "providerRegion"
  | "nodeIp"
  | "capacity"
  | "internalScore"
  | "endpoint"
  | "serverPublicKey"
  | "clientAddress"
  | "dns"
  | "allowedIps";

type DiscoveryKey =
  | keyof CountryDiscoveryModel
  | keyof CountryAvailability
  | keyof AutopilotAvailability;
type LeakedKey = Extract<DiscoveryKey, ForbiddenDiscoveryKey>;
const noInfrastructureKeyCanCompile: LeakedKey extends never ? true : false =
  true;

describe("VPN model boundary", () => {
  it("keeps discovery limited to country and product quality", () => {
    const discovery: CountryDiscoveryModel = {
      autopilot: { quality: 91, available: true },
      countries: [{ countryCode: "DE", quality: 84, available: true }],
    };

    expect(noInfrastructureKeyCanCompile).toBe(true);
    expect(Object.keys(discovery)).toEqual(["autopilot", "countries"]);
    expect(Object.keys(discovery.countries[0])).toEqual([
      "countryCode",
      "quality",
      "available",
    ]);
  });

  it("keeps required tunnel details in the native transport contract", () => {
    const transport: WireGuardTransportConfiguration = {
      endpoint: { ipv4: "204.48.17.50", port: 51820 },
      serverPublicKey: "server-public-key",
      clientAddress: "10.77.0.2/32",
      dns: ["1.1.1.1", "1.0.0.1"],
      allowedIps: ["0.0.0.0/0"],
    };

    expect(transport.allowedIps).toEqual(["0.0.0.0/0"]);
    expect(transport.endpoint.ipv4).toBe("204.48.17.50");
  });
});
