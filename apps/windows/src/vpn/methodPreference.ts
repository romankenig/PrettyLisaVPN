const KEY = "prettylisavpn:last-successful-vpn-method";
type PreferenceStorage = Pick<Storage, "getItem" | "setItem">;

/** Device-local method ID only; no account, endpoint, keys or connection history. */
export function createMethodPreference(
  storage: PreferenceStorage | null = null,
) {
  let method: string | null = null;
  try {
    const saved = storage?.getItem(KEY);
    if (saved && /^[a-z][a-z0-9_]{0,63}$/.test(saved)) method = saved;
  } catch {
    /* Optional preference; keep the default order if storage is unavailable. */
  }
  return {
    current: () => method,
    remember(verifiedMethod: string) {
      method = verifiedMethod;
      try {
        storage?.setItem(KEY, verifiedMethod);
      } catch {
        /* A storage failure must not tear down a verified connection. */
      }
    },
  };
}

export function createDeviceMethodPreference() {
  try {
    return createMethodPreference(globalThis.localStorage);
  } catch {
    return createMethodPreference();
  }
}
