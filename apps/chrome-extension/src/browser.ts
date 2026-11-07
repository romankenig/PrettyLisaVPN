import { controlsProxy, proxySettings, type ProxyConfig } from "./model";

const privacy = () =>
  [
    {
      setting: chrome.privacy.network.webRTCIPHandlingPolicy,
      value: "disable_non_proxied_udp",
    },
    { setting: chrome.privacy.network.networkPredictionEnabled, value: false },
  ] as const;
function available(level: string) {
  return [
    "controllable_by_this_extension",
    "controlled_by_this_extension",
  ].includes(level);
}
export async function applyProxy(proxy: ProxyConfig) {
  const details = await chrome.proxy.settings.get({ incognito: false });
  if (!available(details.levelOfControl)) throw new Error("PROXY_CONTROL_LOST");
  for (const { setting, value } of privacy()) {
    const status = await setting.get({ incognito: false });
    if (!available(status.levelOfControl))
      throw new Error("PRIVACY_CONTROL_LOST");
    if (typeof value === "string")
      await chrome.privacy.network.webRTCIPHandlingPolicy.set({
        value,
        scope: "regular_only",
      });
    else
      await chrome.privacy.network.networkPredictionEnabled.set({
        value,
        scope: "regular_only",
      });
  }
  await chrome.proxy.settings.set({
    value: proxySettings(proxy),
    scope: "regular_only",
  });
  await verifyProxy(proxy);
}
export async function clearProxy() {
  await chrome.proxy.settings.clear({ scope: "regular_only" });
  for (const { setting } of privacy())
    await setting.clear({ scope: "regular_only" });
  const result = await chrome.proxy.settings.get({ incognito: false });
  if (result.levelOfControl === "controlled_by_this_extension")
    throw new Error("PROXY_RESTORE_FAILED");
}
export async function verifyProxy(proxy: ProxyConfig) {
  if (
    !controlsProxy(await chrome.proxy.settings.get({ incognito: false }), proxy)
  )
    throw new Error("PROXY_CONTROL_LOST");
  for (const { setting, value } of privacy()) {
    const result = await setting.get({ incognito: false });
    if (
      result.value !== value ||
      result.levelOfControl !== "controlled_by_this_extension"
    )
      throw new Error("PRIVACY_CONTROL_LOST");
  }
}
