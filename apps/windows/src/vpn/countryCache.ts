import {
  isVpnCountriesResponse,
  type VpnCountriesResponse,
} from "../api/client";

// Public catalog only; never credentials, endpoints or the user's actual location.
export function readCountryCache(key: string): VpnCountriesResponse | null {
  try {
    const raw = localStorage.getItem(`prettylisavpn.countries.${key}`);
    if (!raw || raw.length > 100_000) return null;
    const value: unknown = JSON.parse(raw);
    return isVpnCountriesResponse(value) ? value : null;
  } catch {
    return null;
  }
}

export function saveCountryCache(
  key: string,
  data: VpnCountriesResponse,
): void {
  try {
    localStorage.setItem(
      `prettylisavpn.countries.${key}`,
      JSON.stringify(data),
    );
  } catch {
    // Viewing the live catalog must work when storage is unavailable.
  }
}
