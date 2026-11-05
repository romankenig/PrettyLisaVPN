import type { PrivateState } from "./controller";
import type { Session } from "./model";

interface Area {
  get(key: string): Promise<Record<string, unknown>>;
  set(value: Record<string, unknown>): Promise<void>;
}

// Only auth survives browser exit. Lease credentials and OTP form state remain
// in session storage, restricted to extension contexts by background.ts.
export function stateStorage(local: Area, session: Area) {
  return {
    async load(): Promise<Partial<PrivateState> | undefined> {
      const volatile = (await session.get("private")).private as
        PrivateState | undefined;
      const durable = await local.get("auth");
      // Upgrade a running 0.1.0 worker without forcing another OTP.
      const auth = ("auth" in durable ? durable.auth : volatile?.session) as
        Session | null | undefined;
      return volatile || auth
        ? { ...volatile, session: auth ?? undefined }
        : undefined;
    },
    async save(value: PrivateState) {
      // Persist rotation/logout before publishing volatile state. A null marker
      // prevents a stale session record from resurrecting a signed-out account.
      await local.set({ auth: value.session ?? null });
      await session.set({ private: value });
    },
  };
}
