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
      const valid = [...new Set(raw)].filter(
        (id): id is string => typeof id === "string" && ids.includes(id),
      );
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
    randomize(random: () => number = Math.random) {
      const shuffled = [...ids];
      for (let i = shuffled.length - 1; i > 0; i--) {
        const j = Math.floor(random() * (i + 1));
        [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
      }
      const next = shuffled.slice(0, 1 + Math.floor(random() * ids.length));
      const active = selected ?? ids;
      // Make every click visible, even if the random draw repeats the current choice.
      if (
        next.length === active.length &&
        next.every((id, i) => id === active[i])
      ) {
        if (next.length > 1) next.push(next.shift()!);
        else next[0] = ids[(ids.indexOf(next[0]) + 1) % ids.length];
      }
      save(next);
    },
    toggle(id: string) {
      if (!ids.includes(id)) return;
      const active = selected ?? ids;
      const next = active.includes(id)
        ? active.filter((value) => value !== id)
        : [...active, id];
      if (next.length)
        save(
          next.every((value, i) => value === ids[i]) &&
            next.length === ids.length
            ? null
            : next,
        );
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
