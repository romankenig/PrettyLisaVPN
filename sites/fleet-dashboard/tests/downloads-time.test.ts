import test from "node:test";
import assert from "node:assert/strict";
import { clock, date, TIME_ZONE_LABEL } from "../src/time.ts";
import { readClients, downloadUrls } from "../src/downloads.ts";

test("GMT+3 remains fixed, including midnight rollover and summer/winter", () => {
  assert.equal(TIME_ZONE_LABEL, "GMT+3");
  assert.equal(clock("2026-10-28T21:05:00Z"), "00:05");
  assert.match(date("2026-10-28T21:05:00Z", false), /^29 /);
  assert.equal(clock("2026-01-01T10:30:00Z"), "13:30");
  assert.equal(clock("2026-07-01T10:30:00Z"), "13:30");
  assert.equal(date(null), "—");
});

test("downloads tolerate a missing platform and never use catalog-controlled links", () => {
  const client = { version: "0.14.0", published_at: "2026-10-28T12:00:00Z", bytes: 25000000 };
  assert.deepEqual(readClients({ schema: 1, clients: { android: { ...client, url: "https://untrusted.invalid" } } }), { android: client });
  assert.equal(downloadUrls.android, "/dashboard/downloads/android.apk");
  assert.equal(downloadUrls.windows, "/dashboard/downloads/windows.exe");
  assert.deepEqual(readClients({ schema: 1, clients: { android: { ...client, published_at: "invalid" }, windows: { ...client, bytes: -1 } } }), {});
  assert.throws(() => readClients({ clients: {} }));
});
