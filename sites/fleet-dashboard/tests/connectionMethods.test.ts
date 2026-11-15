import { test } from "node:test";
import assert from "node:assert/strict";
import { methodName, readMethodReport } from "../src/connectionMethods.ts";

const fixture = () => ({ generated_at: "2026-11-15T09:00:00Z", methods: [{ id: "wireguard_relay", points: Array.from({ length: 7 }, (_, i) => ({ date: `2026-11-${String(i + 8).padStart(2, "0")}`, score: i === 0 ? 0 : null })), week_score: 0, observed_days: 1, today_score: null, today_code: "PENDING", next_check_at: "2026-11-15T12:00:00Z" }], selection: { active_sessions: 2, items: [{ method: "wireguard_relay", count: 2, share: 100 }] } });
test("method names keep relay distinct and preserve unknown protocols", () => {
  assert.equal(methodName("wireguard"), "WireGuard"); assert.equal(methodName("wireguard_relay"), "WireGuard+");
  assert.equal(methodName("amneziawg_relay"), "AmneziaWG+"); assert.equal(methodName("future"), "future");
});
test("zero, absent history and empty sessions remain distinct", () => {
  const data = fixture(); assert.equal(readMethodReport(data).methods[0].week_score, 0);
  data.selection = { active_sessions: 0, items: [] }; assert.equal(readMethodReport(data).selection.active_sessions, 0);
});
test("reject impossible coverage, duplicate dates and inconsistent shares", () => {
  const coverage = fixture(); coverage.methods[0].observed_days = 7; assert.throws(() => readMethodReport(coverage));
  const dates = fixture(); dates.methods[0].points[1].date = dates.methods[0].points[0].date; assert.throws(() => readMethodReport(dates));
  const share = fixture(); share.selection.items[0].share = 50; assert.throws(() => readMethodReport(share));
  const scores = fixture(); scores.methods[0].today_score = 101 as never; assert.throws(() => readMethodReport(scores));
});
