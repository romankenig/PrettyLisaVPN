import { describe, expect, it } from "vitest";
import { remainingPaidDays } from "../billing/model";

describe("paid period display", () => {
  it("counts partial UTC days without extending access at the exclusive deadline", () => {
    const deadline = "2026-11-30T00:00:00Z";
    const end = Date.parse(deadline);
    expect(remainingPaidDays(deadline, end - 86_400_001)).toBe(2);
    expect(remainingPaidDays(deadline, end - 1)).toBe(1);
    expect(remainingPaidDays(deadline, end)).toBe(0);
    expect(remainingPaidDays(deadline, end + 1)).toBe(0);
    expect(remainingPaidDays(null)).toBeNull();
    expect(remainingPaidDays("invalid")).toBeNull();
  });
});
