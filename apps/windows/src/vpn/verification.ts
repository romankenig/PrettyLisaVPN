import type {
  ProtocolFailure,
  ConnectionResult,
  VpnProtocol,
} from "./protocol";

export function normalizeFailure(code: unknown): ProtocolFailure {
  const codes = [
    "TRANSPORT_TIMEOUT",
    "HANDSHAKE_FAILED",
    "TUNNEL_ESTABLISHED_NO_TRAFFIC",
    "DNS_FAILED",
    "HTTPS_CHECK_FAILED",
    "EGRESS_MISMATCH",
    "ROUTE_LEAK_DETECTED",
    "SERVER_UNREACHABLE",
    "OBFUSCATION_FAILED",
    "UNKNOWN",
  ] as const;
  return codes.find((value) => value === code) ?? "UNKNOWN";
}
/** Bound external runtime calls; timeout can never preserve CONNECTED. */
export async function checkHealth(
  protocol: Pick<VpnProtocol, "health">,
): Promise<ConnectionResult> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      protocol.health(),
      new Promise<ConnectionResult>((resolve) => {
        timer = setTimeout(
          () =>
            resolve({
              tunnel_established: true,
              internet_verified: false,
              failure_code: "TRANSPORT_TIMEOUT",
              diagnostics: {
                status: "UNKNOWN",
                transport_healthy: false,
                tx_bytes: 0,
                rx_bytes: 0,
              },
            }),
          20_000,
        );
      }),
    ]);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
  }
}
