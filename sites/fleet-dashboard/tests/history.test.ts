import test from "node:test";
import assert from "node:assert/strict";
import { hourMeasurements } from "../src/history.ts";

test("hour details preserve individual speeds/ratings and obey node/group selection", () => {
  const at = "2026-10-28T12:00:00Z";
  const value = { observed_at: at, status: "HEALTHY", mode: "SYNTHETIC", quality: 88, download_mbps: 50.5, upload_mbps: 21.2, connection_ms: 500, active_connections: 2 };
  const de = { id: "de", name: "netcup-de-001", history: [{ at, measurements: [value, { ...value, observed_at: "2026-10-28T12:30:00Z", quality: 0, download_mbps: null }] }] };
  const us = { id: "us", name: "digocean-us-001", history: [{ at, measurements: [{ ...value, quality: null }] }] };
  assert.equal(hourMeasurements([de, us], { at }).length, 3);
  assert.equal(hourMeasurements([de, us], { at: "2026-10-28T12:00:00.000Z" }).length, 3);
  const selected = hourMeasurements([de, us], { at, nodeId: "de" });
  assert.deepEqual(selected.map(row => row.quality), [88, 0]);
  assert.deepEqual(selected.map(row => row.download_mbps), [50.5, null]);
  assert.equal(hourMeasurements([us], { at })[0].quality, null);
  assert.deepEqual(hourMeasurements([de], { at: "missing" }), []);
  assert.deepEqual(hourMeasurements([{ id: "legacy", name: "legacy", history: [{ at }] }], { at }), []);
});
