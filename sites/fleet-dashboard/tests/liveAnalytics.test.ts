import { test } from "node:test";
import assert from "node:assert/strict";
import { analyticsChartPoints, readAnalytics, segments, type Analytics } from "../src/analytics.ts";

function fixture(): Analytics {
  const count = { total: 1, complete: true, plans: { DEMO: 0, FREE: 1, PREMIUM: 0, PLATINUM: 0, UNKNOWN: 0 } };
  const point = { date: "2026-11-14", complete: true, dau: count, wau: count, mau: count, new_accounts: 0, verified_sessions: 1, connection_success_percent: 100, settled_attempts: 1, pending_attempts: 0, median_connection_seconds: 2, engagement_percent: 100 };
  const distribution = { bounds_seconds: [10,60,180,300,900], counts: [1,0,0,0,0,0], samples: 1, shares: [100,0,0,0,0,0] };
  return { schema: 1, timezone: "GMT+3", generated_at: "2026-11-15T00:00:00Z", next_update_at: "2026-11-15T21:00:00Z", from_date: point.date, through_date: point.date, full_collection_from: "2026-10-01", observed_from: null, attempts_from: null, history_partial: false, points: [point], methods: {}, live: { partial: true, updated_at: "2026-11-15T12:00:00Z", from_date: "2026-09-15", point: { ...point, date: "2026-11-15", new_accounts: 2 }, summary: {session_duration: distribution, time_to_silence: distribution, mean_session_seconds: 5, duration_unobserved_sessions: 1, silence_unobserved_sessions: 1} } };
}

test("every current metric appends once, without changing history or legacy responses", () => {
  const data = readAnalytics(fixture()), before = structuredClone(data.points);
  const points = analyticsChartPoints(data);
  assert.equal(points.length, 2);
  assert.equal(points[1].new_accounts, 2);
  assert.equal(points[1].dau.total, 1);
  assert.deepEqual(data.points, before);
  delete data.live;
  assert.deepEqual(analyticsChartPoints(readAnalytics(data)), before);
});

test("midnight and a delayed snapshot leave missing dates null, never connected or zero", () => {
  const data = fixture();
  data.live!.point.date = "2026-11-16";
  data.live!.updated_at = "2026-11-15T21:00:00Z";
  const points = analyticsChartPoints(readAnalytics(data));
  assert.deepEqual(points.map(p => p.date), ["2026-11-14", "2026-11-15", "2026-11-16"]);
  assert.equal(points[1].new_accounts, null);
  assert.equal(points[1].dau.total, null);
  assert.equal(segments(points.map(p => p.dau.total)).length, 2);
  data.live!.point.date = "2027-01-30";
  data.live!.updated_at = "2027-01-30T12:00:00Z";
  assert.equal(analyticsChartPoints(readAnalytics(data)).length, 63);
});

test("live contract rejects wrong dates, cohorts, non-finite metrics and broken histograms", () => {
  for (const mutate of [
    (data: Analytics) => { data.live!.updated_at = "2026-11-15T21:00:00Z"; },
    (data: Analytics) => { data.live!.point.date = data.through_date; },
    (data: Analytics) => { data.live!.point.dau = { ...data.live!.point.dau, total: 3 }; },
    (data: Analytics) => { data.live!.point.mean_session_seconds = NaN; },
    (data: Analytics) => { data.live!.summary.session_duration!.counts[0] = -1; },
    (data: Analytics) => { data.live!.summary.session_duration!.samples = 8; },
  ]) {
    const data = fixture(); mutate(data);
    assert.throws(() => readAnalytics(data));
  }
});
