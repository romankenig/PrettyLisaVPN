import test from "node:test";
import assert from "node:assert/strict";
import { clock, date, TIME_ZONE_LABEL } from "../src/time.ts";
import { readClients, downloadUrls, sourceUrls, simulatorUrl, installNotes } from "../src/downloads.ts";

test("GMT+3 remains fixed, including midnight rollover and summer/winter", () => {
  assert.equal(TIME_ZONE_LABEL, "GMT+3");
  assert.equal(clock("2026-10-28T21:05:00Z"), "00:05");
  assert.match(date("2026-10-28T21:05:00Z", false), /^29 /);
  assert.equal(clock("2026-01-01T10:30:00Z"), "13:30");
  assert.equal(clock("2026-07-01T10:30:00Z"), "13:30");
  assert.equal(date(null), "—");
});

test("Simulator link requires its own verified companion; legacy iOS keeps device only", () => {
  const client = { version: "0.1.0", published_at: "2026-11-05T12:00:00Z", bytes: 20000, package_kind: "unsigned-app" };
  const companion = { simulator_url: simulatorUrl, simulator_sha256: "a".repeat(64), simulator_bytes: 19000 };
  const parse = (fields: object) => readClients({ schema: 1, clients: { ios: { ...client, ...fields } } }).ios;
  assert.equal(parse({})?.has_simulator, undefined);
  assert.equal(parse(companion)?.has_simulator, true);
  for (const fields of [{ simulator_url: downloadUrls.ios }, { simulator_url: "https://untrusted.invalid" }, { simulator_sha256: "bad" }, { simulator_bytes: 0 }]) {
    assert.equal(parse({ ...companion, ...fields })?.has_simulator, undefined);
  }
  assert.equal(simulatorUrl, "/dashboard/downloads/ios-simulator.zip");
  assert.match(installNotes.ios, /Appetize/);
});

test("downloads tolerate a missing platform and never use catalog-controlled links", () => {
  const client = { version: "0.14.0", published_at: "2026-10-28T12:00:00Z", bytes: 25000000 };
  assert.deepEqual(readClients({ schema: 1, clients: { android: { ...client, url: "https://untrusted.invalid" } } }), { android: client });
  assert.equal(downloadUrls.android, "/dashboard/downloads/android.apk");
  assert.equal(downloadUrls.windows, "/dashboard/downloads/windows.exe");
  assert.deepEqual(readClients({ schema: 1, clients: { android: { ...client, published_at: "invalid" }, windows: { ...client, bytes: -1 } } }), {});
  assert.throws(() => readClients({ clients: {} }));
  assert.equal(readClients({ schema: 1, clients: { android: { ...client, sources_url: sourceUrls.android, sources_sha256: "a".repeat(64) } } }).android?.has_sources, true);
  assert.equal(readClients({ schema: 1, clients: { android: { ...client, sources_url: "https://untrusted.invalid/source", sources_sha256: "a".repeat(64) } } }).android?.has_sources, undefined);
});

test("download CPU label accepts only the verified phone architecture", () => {
  const client = { version: "0.15.1", published_at: "2026-10-29T12:00:00Z", bytes: 30000000 };
  const parse = (abi: unknown) => readClients({ schema: 1, clients: { android: { ...client, abi } } }).android;
  assert.equal(parse("arm64-v8a")?.abi, "arm64-v8a");
  assert.equal(parse("untrusted")?.abi, undefined);
  assert.equal(parse(undefined)?.abi, undefined);
});

test("Chrome and unsigned Apple packages use fixed links and explicit installation instructions", () => {
  const client = { version: "0.1.0", published_at: "2026-11-05T12:00:00Z", bytes: 20000 };
  const clients = readClients({ schema: 1, clients: {
    chrome: { ...client, package_kind: "unpacked-extension", url: "https://untrusted.invalid" },
    ios: { ...client, package_kind: "unsigned-app", sources_url: sourceUrls.ios, sources_sha256: "a".repeat(64) },
    macos: { ...client, package_kind: "unsigned-app" },
  } });
  assert.deepEqual(Object.keys(clients), ["chrome", "ios", "macos"]);
  assert.equal(clients.ios?.has_sources, true);
  assert.equal(downloadUrls.chrome, "/dashboard/downloads/chrome-extension.zip");
  assert.equal(downloadUrls.ios, "/dashboard/downloads/ios-unsigned.zip");
  assert.equal(downloadUrls.macos, "/dashboard/downloads/macos-unsigned.zip");
  assert.match(installNotes.chrome, /chrome:\/\/extensions/);
  assert.match(installNotes.ios, /подпись и профиль Apple/);
  assert.match(installNotes.macos, /Network Extension/);
  assert.deepEqual(readClients({ schema: 1, clients: { ios: client, chrome: { ...client, package_kind: "store" }, macos: { ...client, package_kind: "simulator" } } }), {});
});
