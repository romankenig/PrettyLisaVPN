import { invoke } from "@tauri-apps/api/core";
export async function getDemoDeviceKey(): Promise<string> {
  const key = await invoke<string>("get_demo_device_key");
  if (!/^[0-9a-f]{64}$/.test(key)) throw new Error("DEMO_IDENTITY_UNAVAILABLE");
  return key;
}
