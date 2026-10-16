import { useState, type ReactNode } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

export function WindowFrame({ children }: { readonly children: ReactNode }) {
  const [error, setError] = useState<string | null>(null);
  async function control(action: "minimize" | "close") {
    if (!isTauri()) return;
    try {
      await getCurrentWindow()[action]();
    } catch {
      setError("Не удалось выполнить действие с окном. Попробуйте снова.");
    }
  }
  return (
    <div className="window-frame">
      <header className="window-titlebar">
        <div className="window-titlebar__drag" data-tauri-drag-region>
          PrettyLisaVPN
        </div>
        <div className="window-controls">
          <button type="button" aria-label="Свернуть" title="Свернуть"
            onClick={() => void control("minimize")}>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3 8h10" />
            </svg>
          </button>
          <button type="button" aria-label="Закрыть" title="Закрыть"
            onClick={() => void control("close")}>
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path d="m4 4 8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>
      </header>
      {error ? <p className="window-error" role="alert">{error}</p> : null}
      <div className="window-content">{children}</div>
    </div>
  );
}
