export type VpnLocationSelection =
  | { readonly mode: "AUTO" }
  | { readonly mode: "COUNTRY"; readonly country_code: string };

export const DEFAULT_VPN_LOCATION_SELECTION: VpnLocationSelection = {
  mode: "AUTO",
};
