import type { CredentialStorage } from "../native/credentialStorage";
import type { ApiClient, MeResponse } from "../api/client";

export interface SessionCredentials {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly refreshToken: string;
  readonly refreshTokenExpiresAt: string;
  readonly sessionId: string;
  readonly userId: string;
  readonly deviceId: string;
  readonly plan: "FREE" | "PREMIUM" | "PLATINUM";
}

export interface ActiveSession {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly sessionId: string;
  readonly userId: string;
  readonly deviceId: string | null;
  readonly plan: "FREE" | "PREMIUM" | "PLATINUM";
  readonly profile: MeResponse | null;
}

export interface AuthenticationSession {
  establish(credentials: SessionCredentials): Promise<void>;
  activateRestored(credentials: RestoredSessionCredentials): void;
  updateProfile(accessToken: string, profile: MeResponse): void;
  current(): ActiveSession | null;
  subscribe(listener: () => void): () => void;
  clear(): Promise<void>;
  bearer(api: Pick<ApiClient, "refresh" | "me">): Promise<string>;
}

export interface RestoredSessionCredentials {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly sessionId: string;
  readonly userId: string;
  readonly plan: "FREE" | "PREMIUM" | "PLATINUM";
  readonly profile: MeResponse;
}

export function createAuthenticationSession(
  credentialStorage: CredentialStorage,
): AuthenticationSession {
  let activeSession: ActiveSession | null = null;
  let expiresAt = 0;
  let generation = 0;
  let writes = Promise.resolve();
  let renewing: Promise<string> | null = null;
  const serialize = <T>(action: () => Promise<T>): Promise<T> => {
    const result = writes.then(action);
    writes = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  };
  const listeners = new Set<() => void>();
  const publish = () => listeners.forEach((listener) => listener());
  return {
    establish(credentials) {
      generation++;
      return serialize(async () => {
        await credentialStorage.save({
          sessionId: credentials.sessionId,
          refreshToken: credentials.refreshToken,
          expiresAt: credentials.refreshTokenExpiresAt,
        });
        activeSession = Object.freeze({
          accessToken: credentials.accessToken,
          accessTokenExpiresIn: credentials.accessTokenExpiresIn,
          sessionId: credentials.sessionId,
          userId: credentials.userId,
          deviceId: credentials.deviceId,
          plan: credentials.plan,
          profile: null,
        });
        expiresAt = Date.now() + credentials.accessTokenExpiresIn * 1000;
        publish();
      });
    },
    activateRestored(credentials) {
      generation++;
      activeSession = Object.freeze({ ...credentials, deviceId: null });
      expiresAt = Date.now() + credentials.accessTokenExpiresIn * 1000;
      publish();
    },
    updateProfile(accessToken, profile) {
      if (activeSession?.accessToken !== accessToken) return;
      activeSession = Object.freeze({
        ...activeSession,
        userId: profile.id,
        plan: profile.plan,
        profile: Object.freeze({ ...profile }),
      });
      publish();
    },
    current() {
      return activeSession;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    clear() {
      generation++;
      return serialize(async () => {
        await credentialStorage.delete();
        activeSession = null;
        publish();
      });
    },
    bearer(api) {
      if (activeSession && Date.now() < expiresAt - 30_000)
        return Promise.resolve(activeSession.accessToken);
      if (renewing) return renewing;
      const expectedGeneration = generation;
      renewing = serialize(async () => {
        const previous = activeSession;
        if (!previous || generation !== expectedGeneration)
          throw new Error("AUTH_INVALID");
        try {
          const stored = await credentialStorage.retrieve();
          if (!stored || stored.sessionId !== previous.sessionId)
            throw new Error("AUTH_INVALID");
          // Remove the one-use refresh credential before consumption. A crash/timeout
          // requires OTP again, and cannot replay an ambiguously consumed credential.
          await credentialStorage.delete();
          const refreshed = await api.refresh({
            session_id: stored.sessionId,
            refresh_token: stored.refreshToken,
          });
          if (generation !== expectedGeneration)
            throw new Error("AUTH_CHANGED");
          if (refreshed.session_id !== previous.sessionId)
            throw new Error("AUTH_INVALID");
          await credentialStorage.save({
            sessionId: refreshed.session_id,
            refreshToken: refreshed.refresh_token,
            expiresAt: refreshed.refresh_token_expires_at,
          });
          if (generation !== expectedGeneration)
            throw new Error("AUTH_CHANGED");
          activeSession = Object.freeze({
            ...previous,
            accessToken: refreshed.access_token,
            accessTokenExpiresIn: refreshed.access_token_expires_in,
          });
          expiresAt = Date.now() + refreshed.access_token_expires_in * 1000;
          publish();
          return refreshed.access_token;
        } catch (error) {
          if (generation === expectedGeneration) {
            activeSession = null;
            publish();
          }
          throw error;
        }
      });
      return renewing.finally(() => {
        renewing = null;
      });
    },
  };
}
