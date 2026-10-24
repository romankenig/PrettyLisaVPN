import type { ConnectionConfig } from "./protocol";

// Public names only. Never copy arbitrary server/config/error strings into progress.
const methods = {
  WIREGUARD: "WireGuard",
  AMNEZIAWG: "AmneziaWG",
  OPENVPN: "OpenVPN",
  MASQUE: "MASQUE",
  VLESS: "VLESS",
  VMESS: "VMess",
  SHADOWSOCKS: "Shadowsocks",
  TROJAN: "Trojan",
  HYSTERIA: "Hysteria",
  HYSTERIA2: "Hysteria 2",
  SSH: "SSH",
  SSTP: "SSTP",
  IPSEC: "IPsec",
  SOFTETHER: "SoftEther",
  OPENCONNECT: "OpenConnect",
} as const;
export type VpnMethodName = (typeof methods)[keyof typeof methods];
export interface ConnectionAttempt {
  readonly method: VpnMethodName | null;
  readonly previousMethod: VpnMethodName | null;
  readonly retry: boolean;
}
export function methodName(config: ConnectionConfig): VpnMethodName | null {
  return Object.hasOwn(methods, config.protocol)
    ? methods[config.protocol as keyof typeof methods]
    : null;
}
export function attemptMessage(attempt: ConnectionAttempt): string {
  if (!attempt.method) return "Пробую другой способ подключения…";
  if (!attempt.retry) return `Пробую ${attempt.method}…`;
  if (attempt.previousMethod === attempt.method)
    return `Пробую другой вариант ${attempt.method}…`;
  if (!attempt.previousMethod) return `Пробую ${attempt.method}…`;
  return `${attempt.previousMethod} не подключился, пробую ${attempt.method}…`;
}
