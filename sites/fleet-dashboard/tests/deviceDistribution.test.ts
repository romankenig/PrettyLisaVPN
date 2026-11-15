import { test } from "node:test";
import assert from "node:assert/strict";
import { deviceChartPoints, deviceSeries, deviceTotal } from "../src/deviceDistribution.ts";
import { readAnalytics, type AnalyticsPoint, type CurrentDevicePoint } from "../src/analytics.ts";

function point(date: string, connections: Record<string, number> | null, users: Record<string, number> | null): AnalyticsPoint {
  const count = {total: 0, complete: true, plans: {DEMO: 0, FREE: 0, PREMIUM: 0, PLATINUM: 0, UNKNOWN: 0}};
  return {date, complete: true, dau: count, wau: count, mau: count, new_accounts: 0, verified_sessions: connections === null ? null : Object.values(connections).reduce((a,b) => a+b, 0), connection_success_percent: null, settled_attempts: null, pending_attempts: null, median_connection_seconds: null, engagement_percent: null, device_platforms: {connections, users}};
}
test("daily device shares use each day's selected measure and preserve absent history", () => {
  const points = [point("2026-11-10", null, null), point("2026-11-11", {}, {}), point("2026-11-12", {ANDROID: 4, WINDOWS: 2}, {ANDROID: 1, WINDOWS: 1}), point("2026-11-13", {WINDOWS: 1}, {WINDOWS: 1})];
  assert.deepEqual(deviceSeries(points, "users", false).map(row => row.values), [[null, 0, 1, 0], [null, 0, 1, 1]]);
  assert.deepEqual(deviceSeries(points, "users", true).map(row => row.values), [[null, null, 50, 0], [null, null, 50, 100]]);
  assert.equal(deviceSeries(points, "connections", true)[0].values[2], 100 * 4 / 6);
  assert.equal(deviceTotal(points[2], "users"), 2);
  assert.equal(deviceTotal(points[2], "connections"), 6);
  assert.equal(deviceTotal({...points[2], device_platforms: undefined}, "users"), null);
});
test("daily parser rejects fractional, inconsistent or missing device counts", () => {
  const p = point("2026-11-12", {ANDROID: 2}, {ANDROID: 1});
  const report = {schema: 1, timezone: "GMT+3", generated_at: "2026-11-13T06:00:00Z", next_update_at: "2026-11-13T21:00:00Z", from_date: p.date, through_date: p.date, points: [p]};
  assert.equal(readAnalytics(report).points[0].device_platforms?.users?.ANDROID, 1);
  for (const devices of [{connections: {ANDROID: 1.5}, users: {}}, {connections: {ANDROID: 2}, users: {ANDROID: 3}}, {connections: null, users: {ANDROID: 1}}, {connections: {ANDROID: 1}, users: {}}, {}]) {
    assert.throws(() => readAnalytics({...report, points: [{...p, device_platforms: devices}]}));
  }
  assert.equal(readAnalytics({...report, points: [{...p, device_platforms: undefined}]}).points[0].device_platforms, undefined);
});

test("today appends a partial bar, with distinct Chrome counts and user/share denominators", () => {
  const history = [point("2026-11-14", {WINDOWS: 4}, {WINDOWS: 2})];
  const today: CurrentDevicePoint = {date: "2026-11-15", partial: true, updated_at: "2026-11-15T10:00:00Z", device_platforms: {connections: {WINDOWS: 1, CHROME_EXTENSION: 3}, users: {WINDOWS: 1, CHROME_EXTENSION: 1}}};
  const displayed = deviceChartPoints(history, today);
  assert.deepEqual(displayed.map(p => [p.date, !!p.partial]), [["2026-11-14", false], ["2026-11-15", true]]);
  assert.deepEqual(deviceSeries(displayed, "users", true).map(s => [s.name, s.values]), [["Windows", [100, 50]], ["Chrome", [0, 50]]]);
  assert.deepEqual(deviceSeries(displayed, "connections", true).map(s => s.values), [[100, 25], [0, 75]]);
  assert.notEqual(deviceSeries(displayed, "users", false)[0].color, deviceSeries(displayed, "users", false)[1].color);
  assert.equal(history.length, 1);
  assert.equal(deviceChartPoints(history), history);
});

test("midnight removes the old partial bar; delayed finalized history remains a gap", () => {
  const history = [point("2026-11-14", {WINDOWS: 4}, {WINDOWS: 2})];
  const today: CurrentDevicePoint = {date: "2026-11-16", partial: true, updated_at: "2026-11-15T21:00:00Z", device_platforms: {connections: {}, users: {}}};
  const points = deviceChartPoints(history, today);
  assert.deepEqual(points.map(p => p.date), ["2026-11-14", "2026-11-15", "2026-11-16"]);
  assert.equal(deviceTotal(points[1], "users"), null);
  assert.equal(deviceTotal(points[2], "users"), 0);
  const finalized = deviceChartPoints([...history, point("2026-11-15", {CHROME_EXTENSION: 2}, {CHROME_EXTENSION: 1})], today);
  assert.equal(deviceTotal(finalized[1], "users"), 1);
  assert.equal(finalized.filter(p => p.partial).length, 1);
  assert.equal(deviceChartPoints([point("2020-01-01", {}, {})], today).length, 63);
});

test("current day parser requires a real GMT+3 day, partial marker and consistent non-null counts", () => {
  const p = point("2026-11-14", {}, {});
  const report = {schema: 1, timezone: "GMT+3", generated_at: "2026-11-15T00:00:00Z", next_update_at: "2026-11-15T21:00:00Z", from_date: p.date, through_date: p.date, points: [p]};
  const today = {date: "2026-11-15", partial: true, updated_at: "2026-11-14T21:00:00Z", device_platforms: {connections: {CHROME_EXTENSION: 2}, users: {CHROME_EXTENSION: 1}}};
  assert.equal(readAnalytics({...report, device_today: today}).device_today?.date, "2026-11-15");
  for (const invalid of [null, {...today, partial: false}, {...today, date: p.date}, {...today, updated_at: "2026-11-14T20:59:59Z"}, {...today, device_platforms: {connections: null, users: null}}, {...today, device_platforms: {connections: {CHROME_EXTENSION: 1}, users: {CHROME_EXTENSION: 2}}}]) {
    assert.throws(() => readAnalytics({...report, device_today: invalid}));
  }
});
