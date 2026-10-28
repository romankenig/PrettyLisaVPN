import { invoke } from "@tauri-apps/api/core";
import type { HttpTransport } from "../native/http";
import type { ConnectionAdapter } from "./protocol";
import type { ConnectedVpnSession } from "./connection";

interface Configuration {
  address: string;
  server_public_key: string;
  endpoint: string;
  mtu: number;
  dns: string[];
  allowed_ips: string[];
}
interface Lease {
  id: string;
  status: "PROVISIONING" | "READY" | "REVOKING" | "CLOSED";
  country: string;
  expires_at: string;
  heartbeat_seconds: number;
  configuration?: Configuration;
}
export interface WireGuardNative {
  prepare(): Promise<string>;
  start(configuration: Configuration): Promise<void>;
  stop(): Promise<void>;
  verify(address: string, id: string, token: string): Promise<boolean>;
  isUp(): Promise<boolean>;
}
export const wireGuardNative: WireGuardNative = {
  prepare: () => invoke("wg_prepare"),
  start: ({ address, server_public_key, endpoint, mtu }) =>
    invoke("wg_start", {
      configuration: { address, server_public_key, endpoint, mtu },
    }),
  stop: () => invoke("wg_stop"),
  verify: (address, sessionId, accessToken) =>
    invoke("wg_verify", { address, sessionId, accessToken }),
  isUp: () => invoke("wg_is_up"),
};
export function createWireGuardAdapter(options: {
  baseUrl: string;
  transport: HttpTransport;
  bearer: () => Promise<string>;
  lost: () => void;
  native?: WireGuardNative;
  viaRelay?: boolean;
}): ConnectionAdapter {
  const native = options.native ?? wireGuardNative;
  const method = options.viaRelay ? "wireguard_relay" : "wireguard";
  const name = options.viaRelay ? "WireGuard+" : "WireGuard";
  const base = new URL("/vpn/wireguard/sessions", options.baseUrl);
  let lease: Lease | null = null;
  let allocated = false;
  let local = false;
  let heartbeat: ReturnType<typeof setTimeout> | undefined;
  let expiry: ReturnType<typeof setTimeout> | undefined;
  let epoch = 0;
  const pause = () => new Promise<void>((resolve) => setTimeout(resolve, 1000));
  const check = (signal: AbortSignal) => signal.throwIfAborted();
  async function call(
    suffix = "",
    method = "GET",
    body?: object,
    request?: string,
  ): Promise<Lease | null> {
    const token = await options.bearer();
    const response = await options.transport(base.href + suffix, {
      method,
      redirect: "error",
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        ...(request ? { "Idempotency-Key": request } : {}),
      },
      ...(method === "POST" ? { body: JSON.stringify(body ?? {}) } : {}),
    });
    if (!response.ok) {
      const value = await response.json().catch(() => null);
      const code = value?.error?.code;
      throw new Error(
        typeof code === "string" && /^[A-Za-z_]{1,64}$/.test(code)
          ? code
          : "VPN_UNAVAILABLE",
      );
    }
    const value = (await response.json()) as Lease | null;
    if (
      value &&
      (!/^[0-9a-f-]{36}$/.test(value.id) ||
        !["PROVISIONING", "READY", "REVOKING", "CLOSED"].includes(
          value.status,
        ) ||
        !Number.isFinite(Date.parse(value.expires_at)) ||
        value.heartbeat_seconds !== 30)
    )
      throw new Error("VPN_INVALID_RESPONSE");
    return value;
  }
  async function closeRemote() {
    lease ??= await call("/current");
    if (!lease) {
      allocated = false;
      return;
    }
    if (lease.status !== "CLOSED") {
      await call(`/${lease.id}`, "DELETE");
      const until = Date.now() + 30_000;
      while ((await call(`/${lease.id}`))?.status !== "CLOSED") {
        if (Date.now() >= until) throw new Error("VPN_CLEANUP_PENDING");
        await pause();
      }
    }
    lease = null;
    allocated = false;
  }
  async function cleanup(recover = false) {
    let localError: unknown;
    try {
      await native.stop();
      local = false;
    } catch (error) {
      localError = error;
    }
    // Revocation is required even after a native/UAC failure. Otherwise the
    // server keeps renewing an abandoned grant and charging the whole account.
    if (recover || allocated || lease) await closeRemote();
    if (localError) throw localError;
  }
  function armDeadline(row: Lease) {
    clearTimeout(expiry);
    expiry = setTimeout(
      options.lost,
      Math.max(
        0,
        Math.min(Date.parse(row.expires_at) - Date.now(), 2_147_000_000),
      ),
    );
  }
  function keepAlive(run: number) {
    heartbeat = setTimeout(async () => {
      try {
        if (run !== epoch || !lease) return;
        const row = await call(`/${lease.id}/heartbeat`, "POST");
        if (run !== epoch) return;
        if (
          !row ||
          !["PROVISIONING", "READY"].includes(row.status) ||
          Date.parse(row.expires_at) <= Date.now() ||
          (local && !(await native.isUp()))
        )
          throw new Error("VPN_ACCESS_ENDED");
        lease = row;
        armDeadline(row);
        keepAlive(run);
      } catch {
        if (run === epoch) options.lost();
      }
    }, 30_000);
  }
  return {
    id: method,
    name,
    recover: () => cleanup(true),
    async connect(selection, signal) {
      await cleanup(true); // Recover only our local tunnel and this device's remote grant.
      check(signal);
      const publicKey = await native.prepare();
      check(signal);
      allocated = true; // An ambiguous POST still requires lookup and confirmed removal.
      lease = await call(
        "",
        "POST",
        {
          public_key: publicKey,
          method,
          country:
            selection.mode === "COUNTRY" ? selection.country_code : "AUTO",
        },
        crypto.randomUUID(),
      );
      if (!lease) throw new Error("VPN_INVALID_RESPONSE");
      const run = ++epoch;
      armDeadline(lease);
      keepAlive(run);
      const until = Date.now() + 60_000;
      while (lease.status === "PROVISIONING") {
        check(signal);
        if (Date.now() >= until) throw new Error("VPN_SETUP_TIMEOUT");
        await pause();
        lease = await call(`/${lease.id}`);
        if (!lease) throw new Error("VPN_INVALID_RESPONSE");
      }
      check(signal);
      if (lease.status !== "READY" || !lease.configuration)
        throw new Error("VPN_SETUP_FAILED");
      const row = lease,
        configuration = lease.configuration;
      await native.start(configuration);
      local = true;
      check(signal);
      // DNS and HTTPS are bound by the native implementation to the allocated tunnel IP.
      let verified = false;
      for (let attempt = 0; attempt < 3 && !verified; attempt++) {
        check(signal);
        await pause();
        try {
          verified = await native.verify(
            configuration.address,
            row.id,
            await options.bearer(),
          );
        } catch {
          if (attempt === 2) throw new Error("VPN_VERIFICATION_FAILED");
        }
      }
      if (!verified) throw new Error("VPN_EGRESS_MISMATCH");
      const session: ConnectedVpnSession = {
        sessionId: row.id,
        countryCode: row.country,
        expiresAt: row.expires_at,
        remainingSeconds: null,
      };
      return {
        connected: true,
        internetVerified: true,
        session,
        details: {
          protocol: name,
          transport: "UDP",
          server: configuration.endpoint,
          encryption: "ChaCha20-Poly1305",
          obfuscation: "none",
          mtu: configuration.mtu,
          dns: configuration.dns,
          clientAddress: configuration.address,
          allowedIps: configuration.allowed_ips,
          serverPublicKey: configuration.server_public_key,
          keepalive: 25,
        },
      };
    },
    async disconnect() {
      epoch++;
      clearTimeout(heartbeat);
      clearTimeout(expiry);
      // Also stop an install that succeeded while its caller was being cancelled.
      await cleanup();
    },
  };
}
