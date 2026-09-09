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
  readonly deviceId: string;
  readonly plan: "FREE" | "PREMIUM";
}

export interface AuthenticationSession {
  establish(credentials: SessionCredentials): Promise<void>;
  current(): ActiveSession | null;
  clear(): Promise<void>;
}

export function createAuthenticationSession(
  credentialStorage: CredentialStorage,
): AuthenticationSession {
  let activeSession: ActiveSession | null = null;
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
    },
    current() {
      return activeSession;
    },
    async clear() {
      await credentialStorage.delete();
      activeSession = null;
    },
  };
}
