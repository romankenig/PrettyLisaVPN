import { ApiError, type ApiClient } from "../api/client";
import type {
  CredentialStorage,
  RefreshCredential,
} from "../native/credentialStorage";

/** Persist the operation before sending it so a lost response or restart is retryable. */
export async function refreshStoredSession(
  api: Pick<ApiClient, "refresh">,
  storage: CredentialStorage,
  stored: RefreshCredential,
  assertCurrent: () => void = () => undefined,
) {
  assertCurrent();
  const pending = stored.rotationId
    ? stored
    : { ...stored, rotationId: crypto.randomUUID() };
  if (!stored.rotationId) await storage.replace(pending);
  assertCurrent();
  const refreshed = await api.refresh({
    session_id: pending.sessionId,
    refresh_token: pending.refreshToken,
    rotation_id: pending.rotationId,
  });
  assertCurrent();
  if (refreshed.session_id !== pending.sessionId)
    throw new ApiError("INVALID_RESPONSE");
  await storage.replace({
    sessionId: refreshed.session_id,
    refreshToken: refreshed.refresh_token,
    expiresAt: refreshed.refresh_token_expires_at,
  });
  assertCurrent();
  return refreshed;
}
