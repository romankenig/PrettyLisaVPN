import { test } from "node:test";
import assert from "node:assert/strict";
import { formatDay, readAnalytics, segments } from "../src/analytics.ts";

test("chart gaps remain gaps; zero remains a real observation", () => {
  assert.deepEqual(segments([null, 0, 2, null, 1]), [[{index: 1, value: 0}, {index: 2, value: 2}], [{index: 4, value: 1}]]);
  assert.match(formatDay("2026-11-01"), /1/);
});
test("aggregate parser requires ordered completed dates and cohorts that add to total", () => {
  const count = { total: 2, plans: { FREE: 1, PREMIUM: 0, PLATINUM: 0, UNKNOWN: 1 }, complete: false };
  const fixture = { schema: 1, timezone: "GMT+3", generated_at: "2026-11-02T00:00:00Z", next_update_at: "2026-11-02T21:00:00Z", from_date: "2026-11-01", through_date: "2026-11-01", points: [{date: "2026-11-01", dau: count, wau: count, mau: count, new_accounts: 0, verified_sessions: null, connection_success_percent: null, settled_attempts: null, pending_attempts: null, median_connection_seconds: null, engagement_percent: 100}] };
  assert.equal(readAnalytics(fixture).points[0].dau.total, 2);
  assert.throws(() => readAnalytics({...fixture, points:[{...fixture.points[0], date:"2026-11-02"}]}));
  assert.throws(() => readAnalytics({...fixture, points:[{...fixture.points[0], dau:{...count, total: 3}}]}));
  assert.throws(() => readAnalytics({...fixture, points:[{...fixture.points[0], engagement_percent: NaN}]}));
});
