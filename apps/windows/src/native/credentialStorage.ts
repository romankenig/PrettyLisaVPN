import { invoke, isTauri } from "@tauri-apps/api/core";

export interface RefreshCredential {
  readonly sessionId: string;
  readonly refreshToken: string;
  readonly expiresAt: string;
  readonly rotationId?: string;
}

export interface CredentialStorage {
  save(credential: RefreshCredential): Promise<void>;
  retrieve(): Promise<RefreshCredential | null>;
  replace(credential: RefreshCredential): Promise<void>;
  delete(): Promise<void>;
}

export class CredentialStorageError extends Error {
  constructor() {
    super("CREDENTIAL_STORAGE_UNAVAILABLE");
    this.name = "CredentialStorageError";
  }
}

interface NativeRefreshCredential {
  readonly session_id: string;
  readonly refresh_token: string;
  readonly expires_at: string;
  readonly rotation_id?: string;
}

type NativeInvoke = <T>(
  command: string,
  args?: Record<string, unknown>,
) => Promise<T>;

export function createCredentialStorage(
  invokeNative: NativeInvoke = invokeCredentialCommand,
): CredentialStorage {
  async function write(command: string, credential: RefreshCredential) {
    try {
      await invokeNative<void>(command, {
        credential: toNativeCredential(credential),
      });
    } catch {
      throw new CredentialStorageError();
    }
  }

  return {
    save: (credential) => write("save_refresh_credential", credential),
    async retrieve() {
      try {
        const value = await invokeNative<unknown>("load_refresh_credential");
        if (value === null) return null;
        if (!isNativeCredential(value)) throw new CredentialStorageError();
        return {
          sessionId: value.session_id,
          refreshToken: value.refresh_token,
          expiresAt: value.expires_at,
          ...(value.rotation_id ? { rotationId: value.rotation_id } : {}),
        };
      } catch {
        throw new CredentialStorageError();
      }
    },
    replace: (credential) => write("replace_refresh_credential", credential),
    async delete() {
      try {
        await invokeNative<void>("delete_refresh_credential");
      } catch {
        throw new CredentialStorageError();
      }
    },
  };
}

function invokeCredentialCommand<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri()) return Promise.reject(new Error("TAURI_REQUIRED"));
  return invoke<T>(command, args);
}

function toNativeCredential(
  credential: RefreshCredential,
): NativeRefreshCredential {
  return {
    session_id: credential.sessionId,
    refresh_token: credential.refreshToken,
    expires_at: credential.expiresAt,
    ...(credential.rotationId ? { rotation_id: credential.rotationId } : {}),
  };
}

function isNativeCredential(value: unknown): value is NativeRefreshCredential {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.session_id === "string" &&
    typeof candidate.refresh_token === "string" &&
    candidate.refresh_token.length > 0 &&
    typeof candidate.expires_at === "string" &&
    Number.isFinite(Date.parse(candidate.expires_at)) &&
    (candidate.rotation_id === undefined ||
      (typeof candidate.rotation_id === "string" &&
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
          candidate.rotation_id,
        )))
  );
}
