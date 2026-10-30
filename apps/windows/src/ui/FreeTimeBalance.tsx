import { useEffect, useState } from "react";
import type { MeResponse } from "../api/client";
import { t, useLanguage } from "../i18n";

export function freeTimeRemaining(
  profile: MeResponse,
  now: number,
): number | null {
  const rights = profile.entitlements;
  const seconds = rights?.free_seconds_usable ?? rights?.free_seconds_remaining;
  const running = rights?.free_running_sessions ?? 0;
  const limit = rights?.daily_vpn_limit_seconds ?? 3600;
  if (
    typeof seconds !== "number" ||
    !Number.isInteger(seconds) ||
    seconds < 0 ||
    !Number.isInteger(limit) ||
    limit < 1 ||
    limit > 86400 ||
    seconds > limit ||
    !Number.isInteger(running) ||
    running < 0 ||
    running > 5
  )
    return null;
  const elapsed = Math.max(
    0,
    Math.min(60, Math.floor((now - (profile.quotaReceivedAt ?? now)) / 1000)),
  );
  return Math.max(0, seconds - elapsed * running);
}

export function FreeTimeBalance({ profile }: { profile: MeResponse }) {
  const language = useLanguage();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (profile.plan !== "FREE") return null;
  const seconds = freeTimeRemaining(profile, now);
  const balance =
    seconds === null
      ? "—"
      : `${Math.floor(seconds / 60)
          .toString()
          .padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
  const resets = Date.parse(profile.entitlements?.free_quota_resets_at ?? "");
  const resetText = Number.isFinite(resets)
    ? new Intl.DateTimeFormat(language, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(resets)
    : null;
  return (
    <div className="free-time-balance">
      <p>
        {t("Осталось сегодня:")}{" "}
        <strong role="timer" aria-label={t("Остаток Free")}>
          {balance}
        </strong>
      </p>
      {resetText ? (
        <p className="field-help">{t(`Обновится: ${resetText}`)}</p>
      ) : null}
    </div>
  );
}
