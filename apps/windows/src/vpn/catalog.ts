const families = [
  ["wireguard", "WireGuard"],
  ["amneziawg", "Amnezia"],
  ["shadowsocks2022", "SS2022"],
  ["vmess", "VMess"],
  ["vless", "VLESS"],
  ["vless_reality", "REALITY"],
  ["hysteria", "Hysteria"],
  ["hysteria2", "Hysteria 2"],
  ["hysteria2_salamander", "Salamander"],
] as const;

export const connectionMethods = families.flatMap(([id, name]) => [
  { id, name, relay: false },
  { id: `${id}_relay`, name: `${name}+`, relay: true },
]);
