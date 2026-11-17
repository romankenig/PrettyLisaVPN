import { invoke, isTauri } from "@tauri-apps/api/core";
import { validateMessageUrl } from "../messages/model";

export interface MessageBrowser {
  open(url: string): Promise<void>;
}
export const messageBrowser: MessageBrowser = {
  async open(raw) {
    const url = validateMessageUrl(raw);
    if (!isTauri()) throw new Error("NATIVE_BROWSER_REQUIRED");
    await invoke("open_message_url", { url });
  },
};
