import {
  API,
  PROBE,
  UUID,
  errorCode,
  validateLease,
  type Account,
  type Country,
  type Lease,
  type Phase,
  type ProxyConfig,
  type Session,
  type Snapshot,
} from "./model";

export interface PrivateState {
  session?: Session;
  otpEmail?: string;
  lease?: Lease;
  pending?: { id: string; key: string; country: string };
  wanted: boolean;
  phase: Phase;
  error: string | null;
  account: Account | null;
  countries: Country[];
  backend: string | null;
  ip: string | null;
}
export interface Ports {
  load(): Promise<Partial<PrivateState> | undefined>;
  save(value: PrivateState): Promise<void>;
  installation(): Promise<string>;
  apply(proxy: ProxyConfig): Promise<void>;
  clear(): Promise<void>;
  verify(proxy: ProxyConfig): Promise<void>;
  fetch: typeof fetch;
  sleep(ms: number): Promise<void>;
}
export class Controller {
  state: PrivateState = {
    wanted: false,
    phase: "DISCONNECTED",
    error: null,
    account: null,
    countries: [],
    backend: null,
    ip: null,
  };
  private refresh?: Promise<void>;
  private cancelled = false;
  constructor(private readonly io: Ports) {}
  async init() {
    this.state = { ...this.state, ...(await this.io.load()) };
    if (!this.state.session) {
      this.state.wanted = false;
    }
    // Browser exit drops lease credentials, while Chrome proxy settings persist.
    // Keep auth but remove stale overrides; reconnect requires a fresh lease.
    if (!this.state.wanted) await this.io.clear();
    // A stored badge is not evidence after worker suspension or network changes.
    this.state.phase = this.state.wanted ? "VERIFYING" : "DISCONNECTED";
    await this.persist();
  }
  private persist() {
    return this.io.save(this.state);
  }
  snapshot(): Snapshot {
    return {
      phase: this.state.phase,
      error: this.state.error,
      signedIn: Boolean(this.state.session),
      otpEmail: this.state.session ? null : (this.state.otpEmail ?? null),
      account: this.state.account,
      countries: this.state.countries,
      backend: this.state.backend,
      ip: this.state.phase === "CONNECTED" ? this.state.ip : null,
      country: this.state.lease?.country ?? null,
      expires: this.state.lease?.expires_at ?? null,
      cleanupPending:
        !this.state.wanted && Boolean(this.state.lease || this.state.pending),
    };
  }
  async fail(error: unknown) {
    this.state.phase = "FAILED";
    this.state.error = errorCode(error);
    this.state.ip = null;
    await this.persist();
  }
  cancel() {
    this.cancelled = true;
    this.state.wanted = false;
  }
  private async request(
    path: string,
    options: RequestInit = {},
    authenticated = true,
    retry = true,
    origin: typeof API | typeof PROBE = API,
  ): Promise<unknown> {
    const headers = new Headers(options.headers);
    if (authenticated) {
      if (!this.state.session) throw new Error("SIGN_IN_REQUIRED");
      headers.set("Authorization", "Bearer " + this.state.session.access_token);
      if (path.startsWith("/vpn/"))
        headers.set("X-PrettyLisaVPN-Proxy-IP", "1");
    }
    let response: Response;
    try {
      response = await this.io.fetch(origin + path, {
        ...options,
        headers,
        credentials: "omit",
        redirect: "error",
        cache: "no-store",
        signal: AbortSignal.timeout(15000),
      });
    } catch {
      throw new Error("NETWORK_ERROR");
    }
    if (response.status === 401 && authenticated && retry) {
      this.refresh ??= this.refreshSession().finally(() => {
        this.refresh = undefined;
      });
      await this.refresh;
      return this.request(path, options, authenticated, false, origin);
    }
    let value: unknown;
    const raw = await response.text();
    if (raw.length > 262144) throw new Error("INVALID_RESPONSE");
    try {
      value = JSON.parse(raw);
    } catch {
      throw new Error("INVALID_RESPONSE");
    }
    if (!response.ok) {
      const code = (value as { error?: { code?: string } })?.error?.code;
      if (
        (response.status === 401 &&
          (authenticated || path === "/auth/refresh")) ||
        (response.status === 403 &&
          [
            "ACCOUNT_UNAVAILABLE",
            "USER_BLOCKED",
            "DEVICE_REVOKED",
            "AUTH_INVALID",
          ].includes(code?.toUpperCase() ?? ""))
      ) {
        // A definitively ended auth session must not leave the user trapped in
        // an unusable signed-in screen. Server-side principal checks/TTL revoke
        // any old grant independently; a new login can recover its cleanup.
        this.cancel();
        await this.io.clear();
        delete this.state.session;
        delete this.state.lease;
        delete this.state.pending;
        this.state.account = null;
        this.state.countries = [];
        this.state.phase = "DISCONNECTED";
        this.state.error = "SIGN_IN_REQUIRED";
        await this.persist();
        throw new Error("SIGN_IN_REQUIRED");
      }
      if (response.status === 429) throw new Error("RATE_LIMITED");
      throw new Error(
        typeof code === "string" && /^[a-zA-Z][a-zA-Z0-9_]{0,63}$/.test(code)
          ? code.toUpperCase()
          : "REQUEST_FAILED",
      );
    }
    return value;
  }
  private json(value: unknown): RequestInit {
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(value),
    };
  }
  private acceptSession(value: unknown) {
    const session = value as Session;
    if (
      !session ||
      !UUID.test(session.session_id) ||
      typeof session.access_token !== "string" ||
      !session.access_token ||
      typeof session.refresh_token !== "string" ||
      !session.refresh_token
    )
      throw new Error("INVALID_RESPONSE");
    this.state.session = { ...this.state.session, ...session };
  }
  private async refreshSession() {
    const session = this.state.session;
    if (!session) throw new Error("SIGN_IN_REQUIRED");
    const value = await this.request(
      "/auth/refresh",
      this.json({
        session_id: session.session_id,
        refresh_token: session.refresh_token,
      }),
      false,
    );
    this.acceptSession(value);
    await this.persist();
  }
  async requestOtp(email: string) {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254)
      throw new Error("INVALID_EMAIL");
    await this.request("/auth/request-otp", this.json({ email }), false);
    this.state.otpEmail = email;
    await this.persist();
  }
  async resetOtp() {
    delete this.state.otpEmail;
    await this.persist();
  }
  async login(email: string, code: string) {
    if (!/^\d{6}$/.test(code)) throw new Error("INVALID_OTP");
    if (this.state.session) throw new Error("ALREADY_SIGNED_IN");
    this.acceptSession(
      await this.request(
        "/auth/verify-otp",
        this.json({
          email,
          code,
          installation_id: await this.io.installation(),
          platform: "CHROME_EXTENSION",
          device_name: "Chrome",
        }),
        false,
      ),
    );
    this.state.error = null;
    delete this.state.otpEmail;
    await this.persist();
    await this.refreshAccount();
  }
  async refreshAccount() {
    const version = (await this.request("/version", {}, false).catch(
      () => null,
    )) as { application_version?: string } | null;
    this.state.backend =
      typeof version?.application_version === "string"
        ? version.application_version
        : null;
    if (this.state.session) {
      const account = (await this.request("/me")) as Account;
      if (
        !account ||
        !UUID.test(account.id) ||
        typeof account.email !== "string" ||
        !["FREE", "PREMIUM", "PLATINUM"].includes(account.plan)
      )
        throw new Error("INVALID_RESPONSE");
      this.state.account = account;
      const countries = (await this.request(
        "/vpn/countries?method=https_proxy",
      )) as { countries: Country[] };
      if (
        !countries ||
        !Array.isArray(countries.countries) ||
        countries.countries.some(
          (c) =>
            !/^[A-Z]{2}$/.test(c.country_code) ||
            typeof c.available !== "boolean",
        )
      )
        throw new Error("INVALID_RESPONSE");
      this.state.countries = countries.countries;
    }
    await this.persist();
  }
  private async recover() {
    if (!this.state.lease && this.state.pending) {
      const current = await this.request("/vpn/sessions/current");
      if (current) this.state.lease = validateLease(current);
      else {
        const { key, id, country } = this.state.pending;
        this.state.lease = validateLease(
          await this.request("/vpn/sessions", {
            ...this.json({ country, method: "https_proxy", public_key: key }),
            headers: {
              "Content-Type": "application/json",
              "Idempotency-Key": id,
            },
          }),
        );
      }
      delete this.state.pending;
      await this.persist();
    }
  }
  async connect(country: string) {
    if (!/^(AUTO|[A-Z]{2})$/.test(country)) throw new Error("INVALID_COUNTRY");
    if (!this.state.session) throw new Error("SIGN_IN_REQUIRED");
    if (!this.state.lease && !this.state.pending) {
      const current = await this.request("/vpn/sessions/current");
      if (current) this.state.lease = validateLease(current);
    }
    if (this.state.lease || this.state.pending) {
      await this.disconnect();
      if (this.state.lease || this.state.pending)
        throw new Error("VPN_CLEANUP_PENDING");
    }
    this.cancelled = false;
    this.state.wanted = true;
    this.state.phase = "CONNECTING";
    this.state.error = null;
    const key = btoa(
      String.fromCharCode(...crypto.getRandomValues(new Uint8Array(32))),
    );
    this.state.pending = { id: crypto.randomUUID(), key, country };
    await this.persist();
    await this.recover();
    for (let i = 0; i < 55 && !this.cancelled; i++) {
      const lease = this.state.lease!;
      this.state.lease = validateLease(
        await this.request("/vpn/sessions/" + lease.id),
      );
      await this.persist();
      if (this.state.lease.status === "READY") {
        await this.activate();
        return;
      }
      if (this.state.lease.status !== "PROVISIONING")
        throw new Error(this.state.lease.code ?? "VPN_ACCESS_ENDED");
      await this.io.sleep(1000);
    }
    if (this.cancelled) return;
    throw new Error("CONNECTION_TIMEOUT");
  }
  private async activate() {
    const lease = this.state.lease!;
    if (this.cancelled || !this.state.wanted) return;
    if (Date.parse(lease.expires_at) <= Date.now())
      throw new Error("VPN_SESSION_EXPIRED");
    const config = lease.configuration!;
    this.state.phase = "VERIFYING";
    await this.persist();
    await this.io.apply(config.proxy);
    await this.io.verify(config.proxy);
    await this.verifyTraffic();
  }
  private async verifyTraffic() {
    const lease = this.state.lease!;
    await this.io.verify(lease.configuration!.proxy);
    const proof = (await this.request(
      "/vpn/sessions/" + lease.id + "/probe?nonce=" + crypto.randomUUID(),
      {},
      true,
      true,
      PROBE,
    )) as { verified: boolean; ip: string };
    if (
      !proof ||
      proof.verified !== true ||
      !lease.configuration!.expected_egress_ips.includes(proof.ip)
    )
      throw new Error("EGRESS_MISMATCH");
    if (this.cancelled || !this.state.wanted) return;
    this.state.phase = "CONNECTED";
    this.state.ip = proof.ip;
    this.state.error = null;
    await this.persist();
  }
  async disconnect() {
    this.cancel();
    this.state.phase = "DISCONNECTING";
    this.state.ip = null;
    await this.persist();
    // Clear only this extension's overrides; Chrome restores the preexisting
    // system/enterprise/other-extension policy, rather than forcing DIRECT.
    await this.io.clear();
    try {
      await this.recover();
      if (this.state.lease) {
        const id = this.state.lease.id;
        this.state.lease = validateLease(
          await this.request("/vpn/sessions/" + id, { method: "DELETE" }),
        );
        for (let i = 0; i < 12 && this.state.lease.status !== "CLOSED"; i++) {
          await this.io.sleep(500);
          this.state.lease = validateLease(
            await this.request("/vpn/sessions/" + id),
          );
        }
        if (this.state.lease.status === "CLOSED") delete this.state.lease;
      }
      this.state.error = this.state.lease ? "VPN_CLEANUP_PENDING" : null;
    } catch {
      this.state.error = "VPN_CLEANUP_PENDING";
    }
    this.state.phase = "DISCONNECTED";
    await this.persist();
  }
  async tick() {
    if (!this.state.session) return;
    if (!this.state.wanted) {
      if (this.state.lease || this.state.pending) await this.disconnect();
      return;
    }
    await this.recover();
    if (!this.state.lease) throw new Error("VPN_SESSION_NOT_FOUND");
    const lease = validateLease(
      await this.request(
        "/vpn/sessions/" + this.state.lease.id + "/heartbeat",
        { method: "POST" },
      ),
    );
    this.state.lease = lease;
    await this.persist();
    if (
      lease.status !== "READY" ||
      Date.parse(lease.expires_at) <= Date.now()
    ) {
      if (lease.status !== "PROVISIONING") {
        const reconnect =
          lease.code === "VPN_HEARTBEAT_EXPIRED" && this.state.wanted;
        await this.disconnect();
        if (
          reconnect &&
          this.state.session &&
          !this.state.lease &&
          !this.state.pending
        ) {
          await this.connect(lease.country);
          return;
        }
        this.state.error = lease.code ?? "VPN_ACCESS_ENDED";
        await this.persist();
      }
      return;
    }
    // Recheck actual Chrome ownership and end-to-end egress after wake/network change.
    if (this.state.phase === "CONNECTED") await this.verifyTraffic();
    else await this.activate();
  }
  async logout() {
    await this.disconnect();
    if (this.state.lease || this.state.pending)
      throw new Error("VPN_CLEANUP_PENDING");
    if (this.state.session)
      await this.request("/auth/logout", { method: "POST" });
    delete this.state.session;
    this.state.account = null;
    this.state.countries = [];
    await this.persist();
  }
  async devices() {
    return this.request("/devices");
  }
  async revokeDevice(id: string) {
    if (!UUID.test(id)) throw new Error("INVALID_REQUEST");
    if (id === this.state.session?.device?.id) await this.disconnect();
    const result = await this.request("/devices/" + id, { method: "DELETE" });
    if (id === this.state.session?.device?.id) {
      delete this.state.session;
      this.state.account = null;
      await this.persist();
    }
    return result;
  }
  async billing() {
    return this.request("/billing/overview");
  }
  async support(input: {
    request_id: string;
    subject: string;
    description: string;
  }) {
    if (
      !UUID.test(input.request_id) ||
      input.subject.length > 120 ||
      input.description.length > 4000 ||
      !input.subject.trim() ||
      !input.description.trim() ||
      !this.state.account
    )
      throw new Error("INVALID_REQUEST");
    const body = new FormData();
    body.append(
      "report",
      JSON.stringify({
        ...input,
        reply_email: this.state.account.email,
        diagnostics: null,
      }),
    );
    return this.request("/support/requests", { method: "POST", body });
  }
}
