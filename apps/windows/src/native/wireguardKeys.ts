import { invoke, isTauri } from "@tauri-apps/api/core";

export interface WireGuardKeyManager {
  ensurePublicKey(): Promise<string>;
  loadPublicKey(): Promise<string | null>;
  delete(): Promise<void>;
}

export class WireGuardKeyStorageError extends Error {
  constructor() {
    super("WIREGUARD_KEY_STORAGE_UNAVAILABLE");
    this.name = "WireGuardKeyStorageError";
  }
}

type NativeInvoke = <T>(
  command: string,
  args?: Record<string, unknown>,
) => Promise<T>;

export function createWireGuardKeyManager(
  invokeNative: NativeInvoke = invokeKeyCommand,
): WireGuardKeyManager {
  async function read(command: string): Promise<string | null> {
    try {
      const result = await invokeNative<unknown>(command);
      if (result === null && command === "load_wireguard_public_key")
        return null;
      if (!isPublicKeyResponse(result)) throw new WireGuardKeyStorageError();
      return result.public_key;
    } catch {
      throw new WireGuardKeyStorageError();
    }
  }

  return {
    async ensurePublicKey() {
      const publicKey = await read("ensure_wireguard_public_key");
      if (publicKey === null) throw new WireGuardKeyStorageError();
      return publicKey;
    },
    loadPublicKey: () => read("load_wireguard_public_key"),
    async delete() {
      try {
        await invokeNative<void>("delete_wireguard_key");
      } catch {
        throw new WireGuardKeyStorageError();
      }
    },
  };
}

function invokeKeyCommand<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri()) return Promise.reject(new Error("TAURI_REQUIRED"));
  return invoke<T>(command, args);
}

function isPublicKeyResponse(
  value: unknown,
): value is { readonly public_key: string } {
  if (typeof value !== "object" || value === null) return false;
  const publicKey = (value as Record<string, unknown>).public_key;
  return (
    typeof publicKey === "string" && /^[A-Za-z0-9+/]{43}=$/.test(publicKey)
  );
}
