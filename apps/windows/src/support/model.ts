import type { ActiveSession } from "../auth/session";
import type { VpnConnectionState } from "../vpn/connection";

export interface SupportDiagnostics {
  readonly schema_version: 1;
  readonly collected_at: string;
  readonly frontend_version: string | null;
  readonly backend_version: string | null;
  readonly platform: "WINDOWS";
  readonly language: string;
  readonly timezone: string;
  readonly plan: string | null;
  readonly auth_session_id: string | null;
  readonly vpn: {
    readonly phase: string;
    readonly backend: string;
    readonly tunnel: string;
    readonly session_id: string | null;
    readonly failure_code: string | null;
  };
}

export interface SupportSubmission {
  readonly request_id: string;
  readonly subject: string;
  readonly description: string;
  readonly reply_email: string;
  readonly diagnostics: SupportDiagnostics | null;
  readonly screenshots: readonly File[];
}

// A future backend adapter supplies this port. No recipient or SMTP secrets in UI.
export interface SupportSender {
  send(
    submission: SupportSubmission,
    accessToken: string,
    signal: AbortSignal,
  ): Promise<{ readonly request_id: string }>;
}

export function supportDiagnostics(
  frontend: string,
  backend: string,
  session: ActiveSession | null,
  vpn: VpnConnectionState,
): SupportDiagnostics {
  const version = (value: string) =>
    value === "…" || value === "недоступна" ? null : value;
  return {
    schema_version: 1,
    collected_at: new Date().toISOString(),
    frontend_version: version(frontend),
    backend_version: version(backend),
    platform: "WINDOWS",
    language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    plan: session?.plan ?? null,
    auth_session_id: session?.sessionId ?? null,
    vpn: {
      phase: vpn.phase,
      backend: vpn.backend,
      tunnel: vpn.tunnel,
      session_id: "session" in vpn ? vpn.session?.sessionId ?? null : null,
      failure_code: "failure_code" in vpn ? vpn.failure_code ?? null : null,
    },
  };
}

export const screenshotLimits = {
  count: 3,
  fileBytes: 5 * 1024 * 1024,
  totalBytes: 10 * 1024 * 1024,
} as const;

export async function validateScreenshots(files: readonly File[]) {
  if (files.length > screenshotLimits.count)
    return "можно приложить не более 3 скриншотов";
  if (files.some((file) => file.size > screenshotLimits.fileBytes))
    return "каждый скриншот должен быть не больше 5 МБ";
  if (files.reduce((total, file) => total + file.size, 0) > screenshotLimits.totalBytes)
    return "общий размер скриншотов — не больше 10 МБ";
  for (const file of files) {
    const header = new Uint8Array(await new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = () => reject(new Error("SCREENSHOT_READ_FAILED"));
      reader.readAsArrayBuffer(file.slice(0, 12));
    }));
    const png = [137, 80, 78, 71, 13, 10, 26, 10].every(
      (byte, index) => header[index] === byte,
    );
    const jpeg = header[0] === 255 && header[1] === 216 && header[2] === 255;
    const webp = String.fromCharCode(...header.slice(0, 4)) === "RIFF" &&
      String.fromCharCode(...header.slice(8, 12)) === "WEBP";
    if (!((file.type === "image/png" && png) ||
      (file.type === "image/jpeg" && jpeg) ||
      (file.type === "image/webp" && webp)))
      return "поддерживаются скриншоты PNG, JPEG и WebP";
  }
  return null;
}
