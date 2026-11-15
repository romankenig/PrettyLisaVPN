import { describe, expect, it } from "vitest";
import { parseDevices } from "./devices";

const device = {
  id: "11111111-1111-4111-8111-111111111111",
  installation_id: "22222222-2222-4222-8222-222222222222",
  device_name: "Chrome DEMO",
  platform: "CHROME_EXTENSION",
  status: "ACTIVE",
  is_current: true,
  created_at: "2026-11-15T10:00:00Z",
  updated_at: "2026-11-15T10:00:00Z",
  revoked_at: null,
  last_login_at: null,
};

describe("device API response", () => {
  it("accepts the actual top-level list and a guest's null OTP login time", () => {
    expect(parseDevices([device])).toEqual([
      {
        id: device.id,
        device_name: device.device_name,
        status: "ACTIVE",
        is_current: true,
        created_at: device.created_at,
        last_login_at: null,
      },
    ]);
    expect(parseDevices([])).toEqual([]);
  });

  it("keeps registered login dates and supports an omitted optional login time", () => {
    expect(
      parseDevices([{ ...device, last_login_at: device.created_at }])[0]
        .last_login_at,
    ).toBe(device.created_at);
    const legacy: Partial<typeof device> = { ...device };
    delete legacy.last_login_at;
    expect(parseDevices([legacy])[0].last_login_at).toBeNull();
  });

  it.each([
    undefined,
    null,
    {},
    { devices: [device] },
    "devices",
    [null],
    [{}],
    [device, { ...device, id: "not-a-uuid" }],
    [{ ...device, device_name: {} }],
    [{ ...device, status: null }],
    [{ ...device, is_current: "true" }],
    [{ ...device, created_at: "invalid" }],
    [{ ...device, last_login_at: "invalid" }],
  ])("rejects malformed data before it reaches React: %j", (value) => {
    expect(() => parseDevices(value)).toThrow("INVALID_RESPONSE");
  });
});
