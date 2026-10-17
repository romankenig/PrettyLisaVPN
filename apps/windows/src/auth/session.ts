import type { CredentialStorage } from "../native/credentialStorage";
import type { MeResponse } from "../api/client";

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
  const listeners = new Set<() => void>();
  const publish = () => listeners.forEach((listener) => listener());
  return {
    async establish(credentials) {
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
      publish();
    },
    activateRestored(credentials) {
      activeSession = Object.freeze({ ...credentials, deviceId: null });
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
    async clear() {
      await credentialStorage.delete();
      activeSession = null;
      publish();
    },
  };
}
