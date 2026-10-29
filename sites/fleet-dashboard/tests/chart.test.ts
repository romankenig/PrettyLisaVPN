import test from "node:test";
import assert from "node:assert/strict";
import { activeBars, aggregateSeries, aggregateValues, chartSeries } from "../src/chart.ts";

test("group aggregation weights servers equally, uses median and sum, and reports incomplete coverage", () => {
  const sample = { observed_at: "2026-10-29T10:05:00Z", status: "HEALTHY", mode: "SYNTHETIC", quality: 5, download_mbps: 10, upload_mbps: 20, connection_ms: 100, active_connections: 2 };
  const nodes = [
    { id: "de", name: "DE", history: [{ at: "2026-10-29T10:00:00Z", measurements: [sample, { ...sample, observed_at: "2026-10-29T10:55:00Z", quality: 10, download_mbps: 20, active_connections: 4 }] }] },
    { id: "us", name: "US", history: [{ at: "2026-10-29T10:00:00Z", measurements: [{ ...sample, quality: 90, download_mbps: 40, active_connections: 3 }] }] },
    { id: "ru", name: "RU", history: [{ at: "2026-10-29T10:00:00Z", measurements: [{ ...sample, quality: 100, download_mbps: null, active_connections: 0 }] }] },
  ];
  assert.deepEqual(aggregateSeries(nodes, "speed")[0].segments[0][0], { time: Date.parse("2026-10-29T10:00:00Z"), value: 30, covered: 2, total: 3 });
  assert.equal(aggregateSeries(nodes, "rating")[0].segments[0][0].value, 90);
  assert.equal(aggregateSeries(nodes, "active")[0].segments[0][0].value, 7);
  assert.equal(aggregateSeries(nodes.slice(0, 2), "rating")[0].segments[0][0].value, 50);
  assert.equal(aggregateSeries(nodes.slice(0, 1), "speed")[0].segments[0][0].value, 20);
  assert.deepEqual(aggregateSeries([], "active")[0].segments, []);
  assert.equal(aggregateValues([], "speed"), null);
  assert.equal(aggregateValues([0, 0], "active"), 0);
});

test("aggregate gaps are not filled and a later missing value never reuses an old sample", () => {
  const sample = { observed_at: "2026-10-29T10:01:00Z", status: "HEALTHY", mode: "SYNTHETIC", quality: 90, download_mbps: 10, upload_mbps: 20, connection_ms: 100, active_connections: 0 };
  const node = { id: "de", name: "DE", history: [
    { at: "2026-10-29T10:00:00Z", measurements: [sample] },
    { at: "2026-10-29T11:00:00Z", measurements: [{ ...sample, observed_at: "2026-10-29T11:01:00Z" }, { ...sample, observed_at: "2026-10-29T11:59:00Z", quality: null }] },
    { at: "2026-10-29T12:00:00Z", measurements: [{ ...sample, observed_at: "2026-10-29T12:01:00Z", quality: 0 }] },
  ] };
  assert.deepEqual(aggregateSeries([node], "rating")[0].segments.map(segment => segment.map(point => point.value)), [[90], [0]]);
});

test("active bars retain the last sample per node/hour, zeros and gaps without summing devices", () => {
  const hour = Date.parse("2026-10-29T10:00:00Z");
  const bars = activeBars([
    { nodeId: "de", nodeName: "DE", direction: "active", segments: [[{ time: hour + 500, value: 4 }, { time: hour + 5000, value: 2 }], [{ time: hour + 7200000, value: 0 }]] },
    { nodeId: "us", nodeName: "US", direction: "active", segments: [[{ time: hour + 2000, value: 3 }]] },
  ]);
  assert.deepEqual(bars.map(({ nodeId, hour, value }) => ({ nodeId, hour, value })), [
    { nodeId: "de", hour, value: 2 }, { nodeId: "de", hour: hour + 7200000, value: 0 }, { nodeId: "us", hour, value: 3 },
  ]);
  assert.equal(bars[0].time, hour + 5000);
  assert.deepEqual(activeBars([]), []);
});

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
test("active devices preserve integer zeros, split missing data and respect the selected nodes", () => {
  const sample = { observed_at: "2026-10-28T10:00:00Z", status: "HEALTHY", mode: "SYNTHETIC", quality: null, download_mbps: null, upload_mbps: null, connection_ms: null, active_connections: 0 };
  const nodes = [{ id: "de", name: "DE", history: [{ at: sample.observed_at, measurements: [sample, { ...sample, observed_at: "2026-10-28T11:00:00Z", active_connections: 3 }, { ...sample, observed_at: "2026-10-28T12:00:00Z", active_connections: NaN }, { ...sample, observed_at: "2026-10-28T13:00:00Z", active_connections: 2 }] }] }];
  assert.deepEqual(chartSeries(nodes, "active")[0].segments.map(part => part.map(point => point.value)), [[0, 3], [2]]);
  assert.deepEqual(chartSeries([], "active"), []);
});
