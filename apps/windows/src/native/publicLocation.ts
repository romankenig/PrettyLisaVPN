import { invoke, isTauri } from "@tauri-apps/api/core";
import { createHttpTransport, type HttpTransport } from "./http";

// The public provider rejects browser Origin headers. The native command is
// restricted to two built-in providers with fallback; it accepts no destination.
export function createPublicLocationTransport(): HttpTransport {
  const fallback = createHttpTransport();
  return async (input, init) => {
    const url = input instanceof Request ? input.url : String(input);
    if (!isTauri() || url !== "https://ipwho.is/") {
      return fallback(input, init);
    }
    if (init?.signal?.aborted) {
      throw new Error("PUBLIC_LOCATION_UNAVAILABLE");
    }
    const observation = await invoke("get_public_location");
    if (init?.signal?.aborted) {
      throw new Error("PUBLIC_LOCATION_UNAVAILABLE");
    }
    return new Response(JSON.stringify(observation));
  };
}
