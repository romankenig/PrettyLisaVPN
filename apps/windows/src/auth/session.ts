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

export interface AuthenticationSession {
  establish(credentials: SessionCredentials): void;
  current(): SessionCredentials | null;
  clear(): void;
}

export function createInMemoryAuthenticationSession(): AuthenticationSession {
  let credentials: SessionCredentials | null = null;
  return {
    establish(value) {
      credentials = Object.freeze({ ...value });
    },
    current() {
      return credentials;
    },
    clear() {
      credentials = null;
    },
  };
}

export const authenticationSession = createInMemoryAuthenticationSession();
