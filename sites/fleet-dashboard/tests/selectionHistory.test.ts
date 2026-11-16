import { test } from "node:test";
import assert from "node:assert/strict";
import { readSelectionHistory, selectionSeries, type SelectionHistory } from "../src/selectionHistory.ts";
import { methodName } from "../src/connectionMethods.ts";
import { reportPage, reports } from "../src/reportRoutes.ts";

function fixture(): SelectionHistory {
  return { timezone: "GMT+3", generated_at: "2026-11-16T12:00:00Z", from_date: "2026-11-09", through_date: "2026-11-16", observed_from: "2026-11-10T12:00:00Z", categories: [{id: "wireguard", name: "wireguard"}, {id: "wireguard_relay", name: "wireguard_relay"}], points: Array.from({length:8}, (_, i) => ({date:`2026-11-${String(9+i).padStart(2,"0")}`,partial:i===7,complete:i!==0,counts:i===0?null:i===1?{}:{wireguard:i,wireguard_relay:1},total:i===0?null:i===1?0:i+1,active_sessions:i<2?0:i+1,observed_sessions:i<2?0:i+1,unknown_mode_sessions:0,uncertain_sessions:0})) };
}

test("daily shares use each day's denominator, relay stays separate, and gaps differ from zero", () => {
  const history = readSelectionHistory(fixture());
  const counts = selectionSeries(history, false, methodName), shares = selectionSeries(history, true, methodName);
  assert.deepEqual(counts.map(row => row.name), ["WireGuard", "WireGuard+"]);
  assert.equal(counts[0].values[0], null); assert.equal(counts[0].values[1], 0);
  assert.equal(shares[0].values[0], null); assert.equal(shares[0].values[1], null);
  assert.equal(shares[0].values[2], 100*2/3);
  assert.equal(shares[0].values[7], 87.5);
  assert.equal(shares[1].values[7], 12.5);
});

test("reject invalid daily intervals, counts, coverage and current-day labels", () => {
  for (const mutate of [
    (data: SelectionHistory) => { data.points[7].partial = false; },
    (data: SelectionHistory) => { data.points[6].partial = true; },
    (data: SelectionHistory) => { data.points[2].date = data.points[1].date; },
    (data: SelectionHistory) => { data.points[7].counts!.wireguard = -1; },
    (data: SelectionHistory) => { data.points[7].total = 90; },
    (data: SelectionHistory) => { data.points[0].total = 0; },
    (data: SelectionHistory) => { data.points[7].observed_sessions = 99; },
    (data: SelectionHistory) => { data.generated_at = "2026-11-16T21:00:00Z"; },
    (data: SelectionHistory) => { data.categories.push(data.categories[0]); },
  ]) { const data = fixture(); mutate(data); assert.throws(() => readSelectionHistory(data)); }
});

test("partial service coverage preserves known categories and missing daily data", () => {
  const data = fixture(); data.points[7].unknown_mode_sessions = 1; data.points[7].complete = false;
  const read = readSelectionHistory(data);
  assert.equal(read.points[7].complete, false);
  assert.equal(selectionSeries(read, false, (_, name) => name)[0].values[7], 7);
});

test("colliding method colors stay distinct, reserve UNKNOWN gray and survive unit/order changes", () => {
  const data = fixture();
  data.categories = ["amneziawg", "https_proxy", "hysteria", "shadowsocks2022", "sstp_relay", "vless_reality_relay", "wireguard", "wireguard_relay", "hysteria2", "UNKNOWN"].map(id => ({id, name:id}));
  const series = selectionSeries(data, false, methodName);
  assert.equal(new Set(series.map(row => row.color)).size, data.categories.length);
  assert.equal(series.find(row => row.name === "UNKNOWN")!.color, "#9c9c9c");
  data.categories.reverse();
  const byName = (rows: typeof series) => Object.fromEntries(rows.map(row => [row.name, row.color]));
  assert.deepEqual(byName(selectionSeries(data, true, methodName)), byName(series));
});

test("three stability pages and product analytics retain direct URLs and trailing slashes", () => {
  assert.equal(reports.length, 5);
  for (const report of reports) {
    assert.equal(reportPage(report.path), report.id);
    assert.equal(reportPage(report.path.replace(/\/$/, "") + "/"), report.id);
  }
  assert.equal(reportPage("/dashboard"), "servers");
});
