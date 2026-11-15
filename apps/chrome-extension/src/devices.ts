import { UUID, type Device } from "./model";

const validDate = (value: unknown): value is string =>
  typeof value === "string" && Number.isFinite(Date.parse(value));

// GET /devices returns a top-level list for registered and DEMO accounts alike.
export function parseDevices(value: unknown): Device[] {
  if (!Array.isArray(value)) throw new Error("INVALID_RESPONSE");
  return value.map((item: unknown) => {
    if (!item || typeof item !== "object" || Array.isArray(item))
      throw new Error("INVALID_RESPONSE");
    const row = item as Record<string, unknown>;
    if (
      typeof row.id !== "string" ||
      !UUID.test(row.id) ||
      typeof row.device_name !== "string" ||
      typeof row.status !== "string" ||
      typeof row.is_current !== "boolean" ||
      !validDate(row.created_at) ||
      (row.last_login_at != null && !validDate(row.last_login_at))
    )
      throw new Error("INVALID_RESPONSE");
    return {
      id: row.id,
      device_name: row.device_name,
      status: row.status,
      is_current: row.is_current,
      created_at: row.created_at,
      last_login_at: row.last_login_at ?? null,
    };
  });
}
