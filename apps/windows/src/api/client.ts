export interface BackendVersion {
  application_name: string;
  application_version: string;
  environment: string;
}
export class ApiError extends Error {
  constructor(
    public readonly code: "NETWORK_ERROR" | "HTTP_ERROR" | "INVALID_RESPONSE",
  ) {
    super(code);
  }
}
export function createApiClient(
  baseUrl: string,
  transport: typeof fetch = globalThis.fetch,
) {
  return {
    async getVersion(signal?: AbortSignal): Promise<BackendVersion> {
      let response: Response;
      try {
        response = await transport(baseUrl + "/version", {
          signal,
          credentials: "omit",
        });
      } catch {
        throw new ApiError("NETWORK_ERROR");
      }
      if (!response.ok) throw new ApiError("HTTP_ERROR");
      try {
        const data: unknown = await response.json();
        if (
          !data ||
          typeof data !== "object" ||
          !("application_name" in data) ||
          typeof data.application_name !== "string" ||
          !("application_version" in data) ||
          typeof data.application_version !== "string" ||
          !("environment" in data) ||
          typeof data.environment !== "string"
        )
          throw new Error();
        return data as BackendVersion;
      } catch {
        throw new ApiError("INVALID_RESPONSE");
      }
    },
  };
}
