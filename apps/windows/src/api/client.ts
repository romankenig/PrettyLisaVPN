import type { ConnectionConfig } from "../vpn/protocol";
import type { HttpTransport } from "../native/http";

export interface BackendHealth {
  readonly status: "ok";
}

export interface BackendVersion {
  readonly application_name: string;
  readonly application_version: string;
  readonly environment: string;
}

export interface RequestOtpResponse {
  readonly status: "accepted";
}

export interface VerifyOtpRequest {
  readonly email: string;
  readonly code: string;
  readonly installation_id: string;
  readonly platform: "WINDOWS";
  readonly device_name: string;
}

export interface VerifyOtpResponse {
  readonly token_type: "bearer";
  readonly access_token: string;
  readonly access_token_expires_in: number;
  readonly refresh_token: string;
  readonly refresh_token_expires_at: string;
  readonly session_id: string;
  readonly user: { readonly id: string };
  readonly device: {
    readonly id: string;
    readonly installation_id: string;
    readonly status: "ACTIVE" | "REVOKED";
  };
  readonly subscription: {
    readonly plan: "FREE" | "PREMIUM";
    readonly status: "ACTIVE" | "CANCELED" | "EXPIRED";
  };
}

export interface RefreshRequest {
  readonly session_id: string;
  readonly refresh_token: string;
}

export interface RefreshResponse {
  readonly token_type: "bearer";
  readonly access_token: string;
  readonly access_token_expires_in: number;
  readonly refresh_token: string;
  readonly refresh_token_expires_at: string;
  readonly session_id: string;
}

export interface MeResponse {
  readonly id: string;
  readonly email: string;
  readonly plan: "FREE" | "PREMIUM";
  readonly active_device_count: number;
}

export interface LogoutResponse {
  readonly status: "logged_out";
}

export type DevicePlatform =
  | "WINDOWS"
  | "MACOS"
  | "LINUX"
  | "ANDROID"
  | "IOS"
  | "ANDROID_TV"
  | "CHROME_EXTENSION";

export interface DeviceResponse {
  readonly id: string;
  readonly installation_id: string;
  readonly device_name: string;
  readonly platform: DevicePlatform;
  readonly status: "ACTIVE" | "REVOKED";
  readonly created_at: string;
  readonly updated_at: string;
  readonly revoked_at: string | null;
  readonly is_current: boolean;
}

export interface RevokeDeviceResponse {
  readonly status: "revoked";
  readonly device: DeviceResponse;
}

export interface VpnCountriesResponse {
  readonly autopilot: {
    readonly quality: number;
    readonly available: boolean;
  };
  readonly countries: readonly {
    readonly country_code: string;
    readonly quality: number;
    readonly available: boolean;
  }[];
}

export type CreateVpnSessionRequest =
  | { readonly mode: "AUTO"; readonly public_key: string }
  | {
      readonly mode: "COUNTRY";
      readonly country_code: string;
      readonly public_key: string;
    };

export interface ActiveVpnSessionResponse {
  readonly candidates?: readonly ConnectionConfig[];
  readonly session_id: string;
  readonly status: "ACTIVE";
  readonly country_code: string;
  readonly expires_at: string | null;
  readonly server_time: string;
  readonly transport: {
    readonly endpoint: { readonly ipv4: string; readonly port: number };
    readonly server_public_key: string;
    readonly client_address: string;
    readonly dns: readonly string[];
    readonly allowed_ips: readonly string[];
  };
}

export interface TerminatedVpnSessionResponse {
  readonly session_id: string;
  readonly status: "EXPIRED" | "DISCONNECTED" | "FAILED";
}

export interface CurrentVpnSessionResponse {
  readonly session: ActiveVpnSessionResponse | null;
}

export type ApiErrorCode =
  | "NETWORK_ERROR"
  | "TIMEOUT"
  | "RATE_LIMITED"
  | "OTP_INVALID"
  | "DEVICE_LIMIT"
  | "DEVICE_NOT_FOUND"
  | "COUNTRY_UNAVAILABLE"
  | "VPN_UNAVAILABLE"
  | "AUTH_FORBIDDEN"
  | "AUTH_INVALID"
  | "SERVER_ERROR"
  | "HTTP_ERROR"
  | "INVALID_RESPONSE";

export class ApiError extends Error {
  constructor(readonly code: ApiErrorCode) {
    super(code);
    this.name = "ApiError";
  }
}

export interface ApiClient {
  getHealth(signal?: AbortSignal): Promise<BackendHealth>;
  getVersion(signal?: AbortSignal): Promise<BackendVersion>;
  requestOtp(email: string, signal?: AbortSignal): Promise<RequestOtpResponse>;
  verifyOtp(
    body: VerifyOtpRequest,
    signal?: AbortSignal,
  ): Promise<VerifyOtpResponse>;
  refresh(body: RefreshRequest, signal?: AbortSignal): Promise<RefreshResponse>;
  me(accessToken: string, signal?: AbortSignal): Promise<MeResponse>;
  logout(accessToken: string, signal?: AbortSignal): Promise<LogoutResponse>;
  listDevices(
    accessToken: string,
    signal?: AbortSignal,
  ): Promise<DeviceResponse[]>;
  revokeDevice(
    accessToken: string,
    deviceId: string,
    signal?: AbortSignal,
  ): Promise<RevokeDeviceResponse>;
  listVpnCountries(
    accessToken: string,
    signal?: AbortSignal,
  ): Promise<VpnCountriesResponse>;
  createVpnSession(
    accessToken: string,
    body: CreateVpnSessionRequest,
    signal?: AbortSignal,
  ): Promise<ActiveVpnSessionResponse>;
  getCurrentVpnSession(
    accessToken: string,
    signal?: AbortSignal,
  ): Promise<CurrentVpnSessionResponse>;
  disconnectVpnSession(
    accessToken: string,
    vpnSessionId: string,
    signal?: AbortSignal,
  ): Promise<TerminatedVpnSessionResponse>;
}

export function createApiClient(
  baseUrl: string,
  transport: HttpTransport,
  timeoutMs: number,
): ApiClient {
  async function requestJson(
    path: string,
    init: Pick<RequestInit, "method" | "headers" | "body">,
    signal?: AbortSignal,
  ): Promise<unknown> {
    const controller = new AbortController();
    let timedOut = false;
    const abortFromCaller = () => controller.abort();

    if (signal?.aborted) {
      controller.abort();
    } else {
      signal?.addEventListener("abort", abortFromCaller, { once: true });
    }

    let rejectOnAbort: () => void = () => undefined;
    const aborted = new Promise<never>((_, reject) => {
      rejectOnAbort = () =>
        reject(new ApiError(timedOut ? "TIMEOUT" : "NETWORK_ERROR"));
      if (controller.signal.aborted) {
        rejectOnAbort();
      } else {
        controller.signal.addEventListener("abort", rejectOnAbort, {
          once: true,
        });
      }
    });

    const timer = globalThis.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    const request = (async () => {
      let response: Response;
      try {
        response = await transport(`${baseUrl}${path}`, {
          ...init,
          signal: controller.signal,
          credentials: "omit",
        });
      } catch {
        throw new ApiError(timedOut ? "TIMEOUT" : "NETWORK_ERROR");
      }

      if (!response.ok) {
        const errorCode = await readErrorCode(response);
        if (response.status === 429 && errorCode === "otp_rate_limited") {
          throw new ApiError("RATE_LIMITED");
        }
        if (response.status === 401 && errorCode === "otp_invalid_or_expired") {
          throw new ApiError("OTP_INVALID");
        }
        if (response.status === 409 && errorCode === "device_limit_reached") {
          throw new ApiError("DEVICE_LIMIT");
        }
        if (response.status === 409 && errorCode === "COUNTRY_UNAVAILABLE") {
          throw new ApiError("COUNTRY_UNAVAILABLE");
        }
        if (response.status === 409 && errorCode === "VPN_UNAVAILABLE") {
          throw new ApiError("VPN_UNAVAILABLE");
        }
        if (response.status === 403 && errorCode === "user_blocked") {
          throw new ApiError("AUTH_FORBIDDEN");
        }
        if (
          response.status === 401 &&
          [
            "authentication_required",
            "invalid_refresh_token",
            "invalid_access_token",
            "invalid_session",
          ].includes(String(errorCode))
        ) {
          throw new ApiError("AUTH_INVALID");
        }
        if (response.status === 403 && errorCode === "device_revoked") {
          throw new ApiError("AUTH_INVALID");
        }
        if (response.status === 404 && errorCode === "device_not_found") {
          throw new ApiError("DEVICE_NOT_FOUND");
        }
        if (response.status >= 500) throw new ApiError("SERVER_ERROR");
        throw new ApiError("HTTP_ERROR");
      }

      try {
        return await response.json();
      } catch {
        throw new ApiError(timedOut ? "TIMEOUT" : "INVALID_RESPONSE");
      }
    })();

    try {
      return await Promise.race([request, aborted]);
    } finally {
      globalThis.clearTimeout(timer);
      signal?.removeEventListener("abort", abortFromCaller);
      controller.signal.removeEventListener("abort", rejectOnAbort);
    }
  }

  return {
    async getHealth(signal) {
      const value = await requestJson("/health", { method: "GET" }, signal);
      if (!isRecord(value) || value.status !== "ok") {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { status: "ok" };
    },
    async getVersion(signal) {
      const value = await requestJson("/version", { method: "GET" }, signal);
      if (
        !isRecord(value) ||
        typeof value.application_name !== "string" ||
        typeof value.application_version !== "string" ||
        typeof value.environment !== "string"
      ) {
        throw new ApiError("INVALID_RESPONSE");
      }
      return {
        application_name: value.application_name,
        application_version: value.application_version,
        environment: value.environment,
      };
    },
    async requestOtp(email, signal) {
      const value = await requestJson(
        "/auth/request-otp",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ email }),
        },
        signal,
      );
      if (!isRecord(value) || value.status !== "accepted") {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { status: "accepted" };
    },
    async verifyOtp(body, signal) {
      const value = await requestJson(
        "/auth/verify-otp",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
      if (!isVerifyOtpResponse(value)) throw new ApiError("INVALID_RESPONSE");
      return value;
    },
    async refresh(body, signal) {
      const value = await requestJson(
        "/auth/refresh",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(body),
        },
        signal,
      );
      if (!isRefreshResponse(value)) throw new ApiError("INVALID_RESPONSE");
      return value;
    },
    async me(accessToken, signal) {
      const value = await requestJson(
        "/me",
        {
          method: "GET",
          headers: { authorization: `Bearer ${accessToken}` },
        },
        signal,
      );
      if (!isMeResponse(value)) throw new ApiError("INVALID_RESPONSE");
      return value;
    },
    async logout(accessToken, signal) {
      const value = await requestJson(
        "/auth/logout",
        {
          method: "POST",
          headers: { authorization: `Bearer ${accessToken}` },
        },
        signal,
      );
      if (!isRecord(value) || value.status !== "logged_out") {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { status: "logged_out" };
    },
    async listDevices(accessToken, signal) {
      const value = await requestJson(
        "/devices",
        {
          method: "GET",
          headers: { authorization: `Bearer ${accessToken}` },
        },
        signal,
      );
      if (!Array.isArray(value) || !value.every(isDeviceResponse)) {
        throw new ApiError("INVALID_RESPONSE");
      }
      return value;
    },
    async revokeDevice(accessToken, deviceId, signal) {
      const value = await requestJson(
        `/devices/${encodeURIComponent(deviceId)}`,
        {
          method: "DELETE",
          headers: { authorization: `Bearer ${accessToken}` },
        },
        signal,
      );
      if (
        !isRecord(value) ||
        value.status !== "revoked" ||
        !isDeviceResponse(value.device)
      ) {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { status: "revoked", device: value.device };
    },
    async listVpnCountries(accessToken, signal) {
      const value = await requestJson(
        "/vpn/countries",
        {
          method: "GET",
          headers: { authorization: `Bearer ${accessToken}` },
        },
        signal,
      );
      if (!isVpnCountriesResponse(value)) {
        throw new ApiError("INVALID_RESPONSE");
      }
      return value;
    },
    async createVpnSession(accessToken, body, signal) {
      const value = await requestJson(
        "/vpn/sessions",
        {
          method: "POST",
          headers: {
            authorization: `Bearer ${accessToken}`,
            "x-vpn-candidates": "1",
            "content-type": "application/json",
          },
          body: JSON.stringify(body),
        },
        signal,
      );
      if (!isActiveVpnSessionResponse(value)) {
        throw new ApiError("INVALID_RESPONSE");
      }
      return value;
    },
    async getCurrentVpnSession(accessToken, signal) {
      const value = await requestJson(
        "/vpn/sessions/current",
        {
          method: "GET",
          headers: {
            authorization: `Bearer ${accessToken}`,
            "x-vpn-candidates": "1",
          },
        },
        signal,
      );
      if (
        !hasOnlyKeys(value, ["session"]) ||
        (value.session !== null && !isActiveVpnSessionResponse(value.session))
      ) {
        throw new ApiError("INVALID_RESPONSE");
      }
      return { session: value.session };
    },
    async disconnectVpnSession(accessToken, vpnSessionId, signal) {
      if (!isUuid(vpnSessionId)) throw new ApiError("INVALID_RESPONSE");
      const value = await requestJson(
        `/vpn/sessions/${encodeURIComponent(vpnSessionId)}`,
        {
          method: "DELETE",
          headers: { authorization: `Bearer ${accessToken}` },
        },
        signal,
      );
      if (!isTerminatedVpnSessionResponse(value)) {
        throw new ApiError("INVALID_RESPONSE");
      }
      return value;
    },
  };
}

function isActiveVpnSessionResponse(
  value: unknown,
): value is ActiveVpnSessionResponse {
  return (
    hasOnlyKeys(value, [
      "session_id",
      "status",
      "country_code",
      "expires_at",
      "server_time",
      "transport",
      ...(isRecord(value) && Object.hasOwn(value, "candidates")
        ? ["candidates"]
        : []),
    ]) &&
    (value.candidates === undefined ||
      (Array.isArray(value.candidates) &&
        value.candidates.every(isConnectionConfig))) &&
    isUuid(value.session_id) &&
    value.status === "ACTIVE" &&
    /^[A-Z]{2}$/.test(String(value.country_code)) &&
    (value.expires_at === null || isIsoDate(value.expires_at)) &&
    isIsoDate(value.server_time) &&
    isWireGuardTransport(value.transport)
  );
}

function isTerminatedVpnSessionResponse(
  value: unknown,
): value is TerminatedVpnSessionResponse {
  return (
    hasOnlyKeys(value, ["session_id", "status"]) &&
    isUuid(value.session_id) &&
    ["EXPIRED", "DISCONNECTED", "FAILED"].includes(String(value.status))
  );
}

function isVpnCountriesResponse(value: unknown): value is VpnCountriesResponse {
  return (
    hasOnlyKeys(value, ["autopilot", "countries"]) &&
    hasOnlyKeys(value.autopilot, ["quality", "available"]) &&
    isAvailability(value.autopilot) &&
    Array.isArray(value.countries) &&
    value.countries.every(
      (country) =>
        hasOnlyKeys(country, ["country_code", "quality", "available"]) &&
        /^[A-Z]{2}$/.test(String(country.country_code)) &&
        isAvailability(country),
    )
  );
}

function isAvailability(value: unknown): value is {
  readonly quality: number;
  readonly available: boolean;
} {
  return (
    isRecord(value) &&
    typeof value.quality === "number" &&
    Number.isInteger(value.quality) &&
    value.quality >= 0 &&
    value.quality <= 100 &&
    typeof value.available === "boolean" &&
    value.available === value.quality > 0
  );
}

function hasOnlyKeys<T extends string>(
  value: unknown,
  keys: readonly T[],
): value is Record<T, unknown> {
  return (
    isRecord(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((key) => Object.hasOwn(value, key))
  );
}

function isDeviceResponse(value: unknown): value is DeviceResponse {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    isUuid(value.installation_id) &&
    isNonEmptyString(value.device_name) &&
    [
      "WINDOWS",
      "MACOS",
      "LINUX",
      "ANDROID",
      "IOS",
      "ANDROID_TV",
      "CHROME_EXTENSION",
    ].includes(String(value.platform)) &&
    ["ACTIVE", "REVOKED"].includes(String(value.status)) &&
    isIsoDate(value.created_at) &&
    isIsoDate(value.updated_at) &&
    (value.revoked_at === null || isIsoDate(value.revoked_at)) &&
    typeof value.is_current === "boolean"
  );
}

function isRefreshResponse(value: unknown): value is RefreshResponse {
  return (
    isRecord(value) &&
    value.token_type === "bearer" &&
    isNonEmptyString(value.access_token) &&
    isPositiveInteger(value.access_token_expires_in) &&
    isNonEmptyString(value.refresh_token) &&
    isIsoDate(value.refresh_token_expires_at) &&
    isUuid(value.session_id)
  );
}

function isMeResponse(value: unknown): value is MeResponse {
  return (
    isRecord(value) &&
    isUuid(value.id) &&
    isNonEmptyString(value.email) &&
    ["FREE", "PREMIUM"].includes(String(value.plan)) &&
    typeof value.active_device_count === "number" &&
    Number.isInteger(value.active_device_count) &&
    value.active_device_count >= 0
  );
}

function isVerifyOtpResponse(value: unknown): value is VerifyOtpResponse {
  if (
    !isRecord(value) ||
    value.token_type !== "bearer" ||
    !isNonEmptyString(value.access_token) ||
    !isPositiveInteger(value.access_token_expires_in) ||
    !isNonEmptyString(value.refresh_token) ||
    !isIsoDate(value.refresh_token_expires_at) ||
    !isUuid(value.session_id) ||
    !isRecord(value.user) ||
    !isUuid(value.user.id) ||
    !isRecord(value.device) ||
    !isUuid(value.device.id) ||
    !isUuid(value.device.installation_id) ||
    !["ACTIVE", "REVOKED"].includes(String(value.device.status)) ||
    !isRecord(value.subscription) ||
    !["FREE", "PREMIUM"].includes(String(value.subscription.plan)) ||
    !["ACTIVE", "CANCELED", "EXPIRED"].includes(
      String(value.subscription.status),
    )
  ) {
    return false;
  }
  return true;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function isPort(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 1 &&
    value <= 65535
  );
}

function isIpv4(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const parts = value.split(".");
  return (
    parts.length === 4 &&
    parts.every(
      (part) =>
        /^\d{1,3}$/.test(part) && Number(part) >= 0 && Number(part) <= 255,
    )
  );
}

function isIpv4Cidr(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const [address, prefix, extra] = value.split("/");
  return (
    extra === undefined &&
    isIpv4(address) &&
    /^\d{1,2}$/.test(prefix ?? "") &&
    Number(prefix) <= 32
  );
}

function isIpCidr(value: unknown): value is string {
  return (
    isIpv4Cidr(value) ||
    (typeof value === "string" &&
      /^[0-9a-f:]+\/(?:\d|[1-9]\d|1[01]\d|12[0-8])$/i.test(value))
  );
}

function isWireGuardPublicKey(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9+/]{43}=$/.test(value);
}

function isStringArray(
  value: unknown,
  predicate: (item: unknown) => item is string,
): value is string[] {
  return Array.isArray(value) && value.every(predicate);
}

function isIsoDate(value: unknown): value is string {
  return typeof value === "string" && Number.isFinite(Date.parse(value));
}

async function readErrorCode(response: Response): Promise<unknown> {
  try {
    const value: unknown = await response.json();
    if (!isRecord(value) || !isRecord(value.error)) return undefined;
    return value.error.code;
  } catch {
    return undefined;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function isWireGuardTransport(
  value: unknown,
): value is ActiveVpnSessionResponse["transport"] {
  return (
    hasOnlyKeys(value, [
      "endpoint",
      "server_public_key",
      "client_address",
      "dns",
      "allowed_ips",
    ]) &&
    hasOnlyKeys(value.endpoint, ["ipv4", "port"]) &&
    isIpv4(value.endpoint.ipv4) &&
    isPort(value.endpoint.port) &&
    isWireGuardPublicKey(value.server_public_key) &&
    isIpv4Cidr(value.client_address) &&
    isStringArray(value.dns, isIpv4) &&
    value.dns.length > 0 &&
    isStringArray(value.allowed_ips, isIpCidr) &&
    value.allowed_ips.length > 0
  );
}

function isConnectionConfig(value: unknown): value is ConnectionConfig {
  return (
    hasOnlyKeys(value, [
      "country",
      "protocol",
      "transport",
      "port",
      "encryption_mode",
      "obfuscation_mode",
      "mtu",
      "dns_mode",
      "routing_mode",
      ...(isRecord(value) && Object.hasOwn(value, "obfuscation_version")
        ? ["obfuscation_version"]
        : []),
      ...(isRecord(value) && Object.hasOwn(value, "transport_parameters")
        ? ["transport_parameters"]
        : []),
    ]) &&
    (value.obfuscation_version === undefined ||
      (typeof value.obfuscation_version === "number" &&
        Number.isInteger(value.obfuscation_version) &&
        value.obfuscation_version >= 0)) &&
    (value.transport_parameters === undefined ||
      (isRecord(value.transport_parameters) &&
        Object.keys(value.transport_parameters).every(
          (key) => key === "max_datagram_size",
        ) &&
        Object.values(value.transport_parameters).every(
          (item) =>
            typeof item === "number" &&
            Number.isInteger(item) &&
            item >= 1320 &&
            item <= 65507,
        ))) &&
    typeof value.country === "string" &&
    /^[A-Z]{2}$/.test(value.country) &&
    [
      value.protocol,
      value.transport,
      value.encryption_mode,
      value.obfuscation_mode,
      value.dns_mode,
      value.routing_mode,
    ].every(isNonEmptyString) &&
    isPort(value.port) &&
    typeof value.mtu === "number" &&
    Number.isInteger(value.mtu) &&
    value.mtu >= 576 &&
    value.mtu <= 65535
  );
}
