import type { CredentialStorage } from "../native/credentialStorage";
import { ApiError, type ApiClient, type MeResponse } from "../api/client";
import { refreshStoredSession } from "./refresh";

export interface SessionCredentials {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly refreshToken: string;
  readonly refreshTokenExpiresAt: string;
  readonly sessionId: string;
  readonly userId: string;
  readonly deviceId: string;
  readonly plan: "DEMO" | "FREE" | "PREMIUM" | "PLATINUM";
}

export interface ActiveSession {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly sessionId: string;
  readonly userId: string;
  readonly deviceId: string | null;
  readonly plan: "DEMO" | "FREE" | "PREMIUM" | "PLATINUM";
  readonly profile: MeResponse | null;
}

export interface AuthenticationSession {
  establish(credentials: SessionCredentials): Promise<void>;
  activateRestored(credentials: RestoredSessionCredentials): void;
  updateProfile(accessToken: string, profile: MeResponse): void;
  current(): ActiveSession | null;
  subscribe(listener: () => void): () => void;
  clear(): Promise<void>;
  bearer(
    api: Pick<ApiClient, "refresh" | "me">,
    rejectedToken?: string,
  ): Promise<string>;
}

export interface RestoredSessionCredentials {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly sessionId: string;
  readonly userId: string;
  readonly plan: "DEMO" | "FREE" | "PREMIUM" | "PLATINUM";
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
    bearer(api, rejectedToken) {
      if (rejectedToken && activeSession?.accessToken === rejectedToken)
        expiresAt = 0;
      if (activeSession && Date.now() < expiresAt - 30_000)
        return Promise.resolve(activeSession.accessToken);
      if (renewing) return renewing;
      const expectedGeneration = generation;
      renewing = serialize(async () => {
        const previous = activeSession;
        if (!previous || generation !== expectedGeneration)
          throw new ApiError("AUTH_INVALID");
        try {
          const stored = await credentialStorage.retrieve();
          if (
            !stored ||
            stored.sessionId !== previous.sessionId ||
            Date.parse(stored.expiresAt) <= Date.now()
          )
            throw new ApiError("AUTH_INVALID");
          const refreshed = await refreshStoredSession(
            api,
            credentialStorage,
            stored,
            () => {
              if (generation !== expectedGeneration)
                throw new Error("AUTH_CHANGED");
            },
          );
          activeSession = Object.freeze({
            ...previous,
            accessToken: refreshed.access_token,
            accessTokenExpiresIn: refreshed.access_token_expires_in,
          });
          expiresAt = Date.now() + refreshed.access_token_expires_in * 1000;
          publish();
          return refreshed.access_token;
        } catch (error) {
          if (
            generation === expectedGeneration &&
            error instanceof ApiError &&
            (error.code === "AUTH_INVALID" || error.code === "AUTH_FORBIDDEN")
          ) {
            activeSession = null;
            publish();
            await credentialStorage.delete();
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
