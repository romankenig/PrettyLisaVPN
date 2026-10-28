import test from "node:test";
import assert from "node:assert/strict";
import { chartSeries } from "../src/chart.ts";

test("charts keep exact samples and true zero, split missing/stale intervals and directions", () => {
  const sample = { observed_at: "2026-10-28T10:00:00Z", status: "HEALTHY", mode: "SYNTHETIC", quality: 88, download_mbps: 50, upload_mbps: 25, connection_ms: 100, active_connections: 1 };
  const nodes = [{ id: "de", name: "DE", history: [{ at: sample.observed_at, measurements: [sample, { ...sample, observed_at: "2026-10-28T11:00:00Z", quality: null, download_mbps: null }, { ...sample, observed_at: "2026-10-28T12:00:00Z", quality: 0, download_mbps: 0 }, { ...sample, observed_at: "2026-10-28T14:00:00Z" }] }] }];
  const speed = chartSeries(nodes, "speed");
  assert.equal(speed.length, 2);
  assert.deepEqual(speed[0].segments.map(part => part.map(point => point.value)), [[50], [0], [50]]);
  assert.deepEqual(speed[1].segments.map(part => part.map(point => point.value)), [[25, 25, 25], [25]]);
  assert.deepEqual(chartSeries(nodes, "rating")[0].segments.map(part => part.map(point => point.value)), [[88], [0], [88]]);
  assert.deepEqual(chartSeries([], "rating"), []);
});
