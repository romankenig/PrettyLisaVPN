import assert from "node:assert/strict";
import test from "node:test";
import { parseSpeedMaximum, speedNumber, speedSamples, speedScaleMaximum, speedTooltip, type SpeedPoint } from "../src/activeSpeed.ts";

const direction = { mean_mbps: 2, median_mbps: 1, active_users: 3, bytes: 1250000, active_seconds: 5, reference_mbps: 10, reference_percent: 20, reference_servers: 2 };
const point: SpeedPoint = { at: "2026-11-07T12:00:00Z", download: direction, upload: { ...direction, mean_mbps: null, median_mbps: null, active_users: 0, reference_percent: null }, coverage: { expected_servers: 2, complete_servers: 1, reporting_servers: 1, fraction: 0.5, server_seconds: {} } };
test("lines connect known points at their original times without inventing samples in gaps", () => {
  const missing = { ...point, download: { ...direction, mean_mbps: null, reference_mbps: null } };
  const points = [missing, point, missing, { ...point, download: { ...direction, mean_mbps: 4 } }, missing];
  assert.deepEqual(speedSamples(points, "download", "mean_mbps"), [{ index: 1, value: 2 }, { index: 3, value: 4 }]);
  assert.deepEqual(speedSamples(points, "download", "reference_mbps"), [{ index: 1, value: 10 }, { index: 3, value: 10 }]);
  assert.deepEqual(speedSamples(points, "upload", "mean_mbps"), []);
  assert.equal(points[2].download.mean_mbps, null);
  assert.match(speedTooltip(points[2], 300).join("\n"), /средняя —/);
  assert.equal(speedNumber(null), "—");
  assert.equal(speedNumber(0), "0");
});
test("invalid samples are omitted while an actual zero remains a measured point", () => {
  const points = [NaN, Infinity, 0].map(mean_mbps => ({ ...point, download: { ...direction, mean_mbps } }));
  assert.deepEqual(speedSamples(points, "download", "mean_mbps"), [{ index: 2, value: 0 }]);
  assert.deepEqual(speedSamples([], "download", "mean_mbps"), []);
});
test("Y scale can fit actual speeds independently for each direction without changing reference or tooltip values", () => {
  assert.equal(speedScaleMaximum([point], "download"), 11);
  assert.equal(speedScaleMaximum([point], "download", true), 2.2);
  assert.equal(speedScaleMaximum([point], "upload", true), 0.1 * 1.1);
  assert.equal(speedScaleMaximum([], "download"), 0.1 * 1.1);
  assert.match(speedTooltip(point, 300).join("\n"), /Ориентир проверки: 10 Мбит\/с/);
});
test("manual Y maximum accepts decimal commas and rejects invalid or unusably small ranges", () => {
  for (const input of ["", " ", "0", "-2", "NaN", "Infinity", "1e999", "0,0001", "one"]) {
    assert.equal(parseSpeedMaximum(input), null, input);
  }
  assert.equal(parseSpeedMaximum("0,001"), 0.001);
  assert.equal(parseSpeedMaximum(" 2,5 "), 2.5);
  assert.equal(parseSpeedMaximum("25.5"), 25.5);
  assert.equal(speedNumber(0.001 / 4, 6), "0,00025");
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
