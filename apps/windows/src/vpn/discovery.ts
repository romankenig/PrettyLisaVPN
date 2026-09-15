/** Product-facing VPN discovery data. Infrastructure topology never belongs here. */
export interface AutopilotAvailability {
  readonly quality: number;
  readonly available: boolean;
}

export interface CountryAvailability {
  readonly countryCode: string;
  readonly quality: number;
  readonly available: boolean;
}

export interface CountryDiscoveryModel {
  readonly autopilot: AutopilotAvailability;
  readonly countries: readonly CountryAvailability[];
}
