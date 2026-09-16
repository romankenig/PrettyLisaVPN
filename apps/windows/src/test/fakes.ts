import { createAuthenticationSession } from "../auth/session";
import type { SessionRestoration } from "../auth/restoration";
import type {
  CredentialStorage,
  RefreshCredential,
} from "../native/credentialStorage";
import type { VpnConnectionOrchestrator } from "../vpn/connection";

export function createTestCredentialStorage(): CredentialStorage {
  let credential: RefreshCredential | null = null;
  return {
    async save(value) {
      credential = { ...value };
    },
    async retrieve() {
      return credential === null ? null : { ...credential };
    },
    async replace(value) {
      credential = { ...value };
    },
    async delete() {
      credential = null;
    },
  };
}

export function createTestAuthenticationSession() {
  return createAuthenticationSession(createTestCredentialStorage());
}

export function createTestSessionRestoration(): SessionRestoration {
  return {
    restore: async () => "unauthenticated",
    retry: async () => "unauthenticated",
  };
}

export function createTestVpnConnection(): VpnConnectionOrchestrator {
  return {
    connect: async () => {
      throw new Error("VPN_CONNECTION_NOT_CONFIGURED_IN_TEST");
    },
  };
}
