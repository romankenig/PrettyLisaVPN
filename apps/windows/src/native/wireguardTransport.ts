/**
 * Native-only tunnel bootstrap contract. These values are operationally visible
 * on the user's machine and must not be promoted into React discovery models.
 */
export interface WireGuardEndpoint {
  readonly ipv4: string;
  readonly port: number;
}

export interface WireGuardTransportConfiguration {
  readonly endpoint: WireGuardEndpoint;
  readonly serverPublicKey: string;
  readonly clientAddress: string;
  readonly dns: readonly string[];
  readonly allowedIps: readonly string[];
}
