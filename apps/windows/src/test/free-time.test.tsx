import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import type { MeResponse } from "../api/client";
import { FreeTimeBalance, freeTimeRemaining } from "../ui/FreeTimeBalance";

const profile: MeResponse = {
  id: "user",
  email: "test@example.com",
  plan: "FREE",
  active_device_count: 2,
  quotaReceivedAt: 1000,
  entitlements: {
    free_seconds_remaining: 0,
    free_seconds_usable: 600,
    free_running_sessions: 2,
    free_quota_resets_at: "2030-01-02T00:00:00Z",
  },
};
it("includes reserved time on other devices and counts down the account balance", () => {
  expect(freeTimeRemaining(profile, 31000)).toBe(540);
  expect(freeTimeRemaining(profile, 400000)).toBe(0);
  expect(freeTimeRemaining(profile, 0)).toBe(600);
  const idle = {
    ...profile,
    entitlements: { ...profile.entitlements, free_running_sessions: 0 },
  };
  expect(freeTimeRemaining(idle, 31000)).toBe(600);
});
it("does not invent an hour for missing/invalid data and hides Free balance on paid plans", () => {
  expect(
    freeTimeRemaining({ ...profile, entitlements: undefined }, 1000),
  ).toBeNull();
  expect(
    freeTimeRemaining(
      { ...profile, entitlements: { free_seconds_usable: 9999 } },
      1000,
    ),
  ).toBeNull();
  const { rerender } = render(
    <FreeTimeBalance profile={{ ...profile, quotaReceivedAt: Date.now() }} />,
  );
  expect(screen.getByRole("timer")).toHaveTextContent("10:00");
  rerender(<FreeTimeBalance profile={{ ...profile, plan: "PREMIUM" }} />);
  expect(screen.queryByRole("timer")).toBeNull();
});
