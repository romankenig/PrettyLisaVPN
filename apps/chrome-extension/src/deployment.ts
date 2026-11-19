export function deployment(api: string) {
  if (
    ![
      "https://api.prettylisavpn.com",
      "https://api.test.prettylisavpn.com",
    ].includes(api)
  )
    throw new Error("INVALID_BACKEND_BASE_URL");
  return {
    api,
    website:
      api === "https://api.test.prettylisavpn.com"
        ? "https://test.prettylisavpn.com"
        : "https://prettylisavpn.com",
  };
}
export const target = deployment(
  import.meta.env.VITE_BACKEND_BASE_URL ?? "https://api.prettylisavpn.com",
);
