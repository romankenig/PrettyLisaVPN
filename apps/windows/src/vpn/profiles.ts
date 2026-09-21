import { validObfuscation } from "./obfuscation";
import type { ConnectionConfig } from "./protocol";

export type ProfileId = "WIREGUARD_UDP" | "OPENVPN_TLS_TCP" | "MASQUE_QUIC";
export interface ConnectionProfile {
  readonly id: ProfileId;
  readonly protocol: string;
  readonly transport: "UDP" | "TCP";
  readonly supported_ports: "ANY" | readonly number[];
  readonly default_port: number;
  readonly encryption: string;
  readonly supports_obfuscation: boolean;
  readonly supports_ipv6: boolean;
  readonly supports_full_tunnel: boolean;
  readonly resembles_ordinary_tls: boolean;
  readonly implementation: string;
}

export const connectionProfiles: Readonly<
  Record<ProfileId, ConnectionProfile>
> = Object.freeze({
  WIREGUARD_UDP: Object.freeze({
    id: "WIREGUARD_UDP",
    protocol: "WIREGUARD",
    transport: "UDP",
    supported_ports: "ANY",
    default_port: 51820,
    encryption: "WIREGUARD",
    supports_obfuscation: true,
    supports_ipv6: false,
    supports_full_tunnel: true,
    resembles_ordinary_tls: false,
    implementation: "WireGuardNT",
  }),
  OPENVPN_TLS_TCP: Object.freeze({
    id: "OPENVPN_TLS_TCP",
    protocol: "OPENVPN",
    transport: "TCP",
    supported_ports: Object.freeze([443]),
    default_port: 443,
    encryption: "TLS_1_3_AES_256_GCM",
    supports_obfuscation: true,
    supports_ipv6: false,
    supports_full_tunnel: true,
    resembles_ordinary_tls: false,
    implementation: "OpenVPN/OpenSSL",
  }),
  MASQUE_QUIC: Object.freeze({
    id: "MASQUE_QUIC",
    protocol: "MASQUE",
    transport: "UDP",
    supported_ports: Object.freeze([443]),
    default_port: 443,
    encryption: "TLS_1_3_QUIC",
    supports_obfuscation: false,
    supports_ipv6: false,
    supports_full_tunnel: true,
    resembles_ordinary_tls: false,
    implementation: "HTTP/3 CONNECT-IP (RFC 9484)",
  }),
});

export function validateProfileConfig(
  profile: ConnectionProfile,
  config: ConnectionConfig,
): boolean {
  return (
    /^[A-Z]{2}$/.test(config.country) &&
    config.protocol === profile.protocol &&
    config.transport === profile.transport &&
    config.encryption_mode === profile.encryption &&
    Number.isInteger(config.port) &&
    config.port >= 1 &&
    config.port <= 65535 &&
    (profile.supported_ports === "ANY" ||
      profile.supported_ports.includes(config.port)) &&
    validObfuscation(config) &&
    config.mtu === 1280 &&
    config.dns_mode === "VPN" &&
    profile.supports_full_tunnel &&
    config.routing_mode === "FULL_TUNNEL"
  );
}

export function createProfileConfig(
  id: ProfileId,
  country: string,
  port = connectionProfiles[id].default_port,
): ConnectionConfig {
  const profile = connectionProfiles[id];
  const config = {
    country,
    protocol: profile.protocol,
    transport: profile.transport,
    port,
    encryption_mode: profile.encryption,
    obfuscation_mode: "NONE",
    mtu: 1280,
    dns_mode: "VPN",
    routing_mode: "FULL_TUNNEL",
  };
  if (!validateProfileConfig(profile, config))
    throw new Error("UNSUPPORTED_CONFIGURATION");
  return config;
}
