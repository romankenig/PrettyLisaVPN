import { invoke, isTauri } from "@tauri-apps/api/core";

declare const installationIdBrand: unique symbol;

export type InstallationId = string & {
  readonly [installationIdBrand]: "InstallationId";
};

export interface InstallationIdProvider {
  getInstallationId(): Promise<InstallationId>;
}

type InstallationIdLoader = () => Promise<unknown>;

const UUID_V4_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export function createInstallationIdProvider(
  load: InstallationIdLoader = loadNativeInstallationId,
): InstallationIdProvider {
  return {
    async getInstallationId() {
      try {
        const value = await load();
        if (typeof value !== "string" || !UUID_V4_PATTERN.test(value)) {
          throw new Error("INVALID_INSTALLATION_ID");
        }
        return value as InstallationId;
      } catch {
        throw new Error("INSTALLATION_ID_UNAVAILABLE");
      }
    },
  };
}

function loadNativeInstallationId(): Promise<unknown> {
  if (!isTauri()) return Promise.reject(new Error("TAURI_REQUIRED"));
  return invoke<string>("get_installation_id");
}

export const installationIdProvider = createInstallationIdProvider();
