import { test } from "node:test";
import assert from "node:assert/strict";
import { deviceSeries, deviceTotal } from "../src/deviceDistribution.ts";
import { readAnalytics, type AnalyticsPoint } from "../src/analytics.ts";

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
