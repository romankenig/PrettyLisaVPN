import { ApiError, type ApiClient } from "../api/client";
import {
  CredentialStorageError,
  type CredentialStorage,
} from "../native/credentialStorage";
import type { AuthenticationSession } from "./session";

export type RestorationResult =
  | "authenticated"
  | "unauthenticated"
  | "temporarily-unavailable"
  | "storage-unavailable";

export interface SessionRestoration {
  restore(): Promise<RestorationResult>;
  retry(): Promise<RestorationResult>;
}

export function createSessionRestoration(
  api: ApiClient,
  storage: CredentialStorage,
  session: AuthenticationSession,
  now: () => number = Date.now,
): SessionRestoration {
  let inFlight: Promise<RestorationResult> | null = null;
  let completed: RestorationResult | null = null;

  const runOnce = () => {
    if (completed !== null) return Promise.resolve(completed);
    if (inFlight !== null) return inFlight;
    inFlight = restoreSession(api, storage, session, now).then((result) => {
      completed = result;
      return result;
    });
    return inFlight.finally(() => {
      inFlight = null;
    });
  };

  return {
    restore: runOnce,
    retry() {
      if (
        completed === "temporarily-unavailable" ||
        completed === "storage-unavailable"
      ) {
        completed = null;
      }
      return runOnce();
    },
  };
}

async function restoreSession(
  api: ApiClient,
  storage: CredentialStorage,
  session: AuthenticationSession,
  now: () => number,
): Promise<RestorationResult> {
  try {
    const stored = await storage.retrieve();
    if (stored === null) return "unauthenticated";
    if (Date.parse(stored.expiresAt) <= now()) {
      return await clearInvalidSession(session);
    }

    const refreshed = await api.refresh({
      session_id: stored.sessionId,
      refresh_token: stored.refreshToken,
    });
    await storage.replace({
      sessionId: refreshed.session_id,
      refreshToken: refreshed.refresh_token,
      expiresAt: refreshed.refresh_token_expires_at,
    });
    const profile = await api.me(refreshed.access_token);
    session.activateRestored({
      accessToken: refreshed.access_token,
      accessTokenExpiresIn: refreshed.access_token_expires_in,
      sessionId: refreshed.session_id,
      userId: profile.id,
      plan: profile.plan,
    });
    return "authenticated";
  } catch (error) {
    if (
      error instanceof ApiError &&
      (error.code === "AUTH_INVALID" || error.code === "AUTH_FORBIDDEN")
    ) {
      return clearInvalidSession(session);
    }
    if (error instanceof CredentialStorageError) return "storage-unavailable";
    return "temporarily-unavailable";
  }
}

async function clearInvalidSession(
  session: AuthenticationSession,
): Promise<RestorationResult> {
  try {
    await session.clear();
    return "unauthenticated";
  } catch {
    return "storage-unavailable";
  }
}
