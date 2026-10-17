export type VpnLocationSelection =
  | { readonly mode: "AUTO" }
  | { readonly mode: "COUNTRY"; readonly country_code: string };

export const DEFAULT_VPN_LOCATION_SELECTION: VpnLocationSelection = {
  mode: "AUTO",
};

// Only a connection preference is persisted, never tokens, IPs or locations.
export function readLocationSelection(userId: string): VpnLocationSelection {
  try {
    const value: unknown = JSON.parse(
      localStorage.getItem(`prettylisavpn.location.${userId}`) ?? "null",
    );
    if (
      typeof value === "object" && value !== null &&
      "mode" in value && value.mode === "COUNTRY" &&
      "country_code" in value && typeof value.country_code === "string" &&
      /^[A-Z]{2}$/.test(value.country_code)
    ) return { mode: "COUNTRY", country_code: value.country_code };
  } catch {
    // Storage may be disabled or contain an older/invalid preference.
  }
  return DEFAULT_VPN_LOCATION_SELECTION;
}

export function saveLocationSelection(userId: string, selection: VpnLocationSelection): void {
  try {
    localStorage.setItem(`prettylisavpn.location.${userId}`, JSON.stringify(selection));
  } catch {
    // An unavailable preference store must not prevent a VPN connection.
  }
}
