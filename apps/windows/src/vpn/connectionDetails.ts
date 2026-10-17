/** Public connection facts only. No credentials, private keys or arbitrary config. */
export interface ConnectionDetails {
  readonly protocol: string;
  readonly transport: string;
  readonly server: string;
  readonly encryption: string;
  readonly obfuscation: string;
  readonly mtu?: number;
  readonly dns?: readonly string[];
  readonly clientAddress?: string;
  readonly allowedIps?: readonly string[];
  readonly serverPublicKey?: string;
  readonly keepalive?: number;
  readonly maxDatagramSize?: number;
}
