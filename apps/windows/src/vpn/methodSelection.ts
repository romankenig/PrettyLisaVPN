import { connectionMethods } from "./catalog";

const KEY = "prettylisavpn:enabled-vpn-methods:v1";
const ids = connectionMethods.map((method) => method.id);
type StoragePort = Pick<Storage, "getItem" | "setItem">;

/** null means all, including newly supported methods after an update. */
export function createMethodSelection(storage: StoragePort | null = null) {
  let selected: readonly string[] | null = null;
  try {
    const raw: unknown = JSON.parse(storage?.getItem(KEY) ?? "null");
    if (Array.isArray(raw)) {
      const valid = ids.filter((id) => raw.includes(id));
      if (valid.length) selected = valid;
    }
  } catch {
    // Corrupt or unavailable preferences retain the default automatic mode.
  }
  const listeners = new Set<() => void>();
  const save = (value: readonly string[] | null) => {
    selected = value;
    try {
      storage?.setItem(KEY, JSON.stringify(value));
    } catch {
      // Keep this process's choice even if persistent storage is unavailable.
    }
    listeners.forEach((listener) => listener());
  };
  return {
    current: () => selected,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    all: () => save(null),
    toggle(id: string) {
      if (!ids.includes(id)) return;
      const active = selected ?? ids;
      const next = active.includes(id)
        ? active.filter((value) => value !== id)
        : ids.filter((value) => value === id || active.includes(value));
      if (next.length) save(next.length === ids.length ? null : next);
    },
  };
}

let deviceSelection: ReturnType<typeof createMethodSelection> | undefined;
export function getDeviceMethodSelection() {
  if (!deviceSelection) {
    try {
      deviceSelection = createMethodSelection(globalThis.localStorage);
    } catch {
      deviceSelection = createMethodSelection();
    }
  }
  return deviceSelection;
}
