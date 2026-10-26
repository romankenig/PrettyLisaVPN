import { wireguard } from "./wireguard";
import { amneziawg } from "./amneziawg";
import { openvpn } from "./openvpn";
import { ipsec } from "./ipsec";
import { sstp } from "./sstp";
import { softether } from "./softether";
import { openconnect } from "./openconnect";
import { shadowsocks } from "./shadowsocks";
import { shadowsocks2022 } from "./shadowsocks2022";
import { vmess } from "./vmess";
import { vless } from "./vless";
import { trojan } from "./trojan";
import { ssh } from "./ssh";
import { hysteria } from "./hysteria";

export const placeholderAdapters = () => [
  wireguard(),
  amneziawg(),
  openvpn(),
  ipsec(),
  sstp(),
  softether(),
  openconnect(),
  shadowsocks(),
  shadowsocks2022(),
  vmess(),
  vless(),
  trojan(),
  ssh(),
  hysteria(),
];
