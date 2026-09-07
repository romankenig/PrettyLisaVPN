import { isTauri } from "@tauri-apps/api/core";
import { getVersion } from "@tauri-apps/api/app";
export interface DesktopAdapter {
  getVersion(): Promise<string>;
}
export const desktopAdapter: DesktopAdapter = {
  getVersion: () =>
    isTauri() ? getVersion() : Promise.resolve("browser-preview"),
};
