import assert from "node:assert/strict";
import test from "node:test";
import { speedNumber, speedSegments, speedTooltip, type SpeedPoint } from "../src/activeSpeed.ts";

const direction = { mean_mbps: 2, median_mbps: 1, active_users: 3, bytes: 1250000, active_seconds: 5, reference_mbps: 10, reference_percent: 20, reference_servers: 2 };
const point: SpeedPoint = { at: "2026-11-07T12:00:00Z", download: direction, upload: { ...direction, mean_mbps: null, median_mbps: null, active_users: 0, reference_percent: null }, coverage: { expected_servers: 2, complete_servers: 1, reporting_servers: 1, fraction: 0.5, server_seconds: {} } };
test("missing samples break lines without carrying values or replacing null with zero", () => {
  const points = [point, { ...point, download: { ...direction, mean_mbps: null } }, point];
  assert.deepEqual(speedSegments(points, "download", "mean_mbps").map(s => s.map(p => p.index)), [[0], [2]]);
  assert.deepEqual(speedSegments(points, "upload", "mean_mbps"), []);
  assert.equal(speedNumber(null), "—");
  assert.equal(speedNumber(0), "0");
});
test("tooltip includes both directions, medians, distinct users, reference percent and completeness", () => {
  const text = speedTooltip(point, 60).join("\n");
  assert.match(text, /медиана 1/);
  assert.match(text, /активных пользователей 3/);
  assert.match(text, /средняя —, медиана —/);
  assert.match(text, /20%/);
  assert.match(text, /Полнота: 50%/);
  assert.match(text, /GMT\+3/);
});
