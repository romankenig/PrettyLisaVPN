import type { CredentialStorage } from "../native/credentialStorage";

export interface SessionCredentials {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly refreshToken: string;
  readonly refreshTokenExpiresAt: string;
  readonly sessionId: string;
  readonly userId: string;
  readonly deviceId: string;
  readonly plan: "FREE" | "PREMIUM";
}

export interface ActiveSession {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly sessionId: string;
  readonly userId: string;
  readonly deviceId: string | null;
  readonly plan: "FREE" | "PREMIUM";
}

export interface AuthenticationSession {
  establish(credentials: SessionCredentials): Promise<void>;
  activateRestored(credentials: RestoredSessionCredentials): void;
  current(): ActiveSession | null;
  subscribe(listener: () => void): () => void;
  clear(): Promise<void>;
}

export interface RestoredSessionCredentials {
  readonly accessToken: string;
  readonly accessTokenExpiresIn: number;
  readonly sessionId: string;
  readonly userId: string;
  readonly plan: "FREE" | "PREMIUM";
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
      });
      publish();
    },
    activateRestored(credentials) {
      activeSession = Object.freeze({ ...credentials, deviceId: null });
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
