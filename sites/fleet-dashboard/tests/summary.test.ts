import test from "node:test";
import assert from "node:assert/strict";
import { selectionSummary } from "../src/summary.ts";

test("current selection has mean speeds, median ratings and summed active devices with coverage", () => {
  const nodes = [
    { quality: 10, latest: { download_mbps: 10, upload_mbps: 0, active_connections: 3 } },
    { quality: 90, latest: { download_mbps: 20, upload_mbps: 10, active_connections: 4 } },
    { quality: 100, latest: { download_mbps: 60, upload_mbps: null, active_connections: 0 } },
    { quality: 0, latest: null },
  ];
  const summary = selectionSummary(nodes);
  assert.deepEqual(summary.download, { value: 30, covered: 3, total: 4 });
  assert.deepEqual(summary.upload, { value: 5, covered: 2, total: 4 });
  assert.deepEqual(summary.rating, { value: 90, covered: 3, total: 4 });
  assert.deepEqual(summary.active, { value: 7, covered: 3, total: 4 });
  assert.equal(selectionSummary(nodes.slice(0, 2)).rating.value, 50);
  assert.equal(selectionSummary([]).active.value, null);
});

test("active totals exclude transit nodes but retain their speed and rating", () => {
  const latest = { download_mbps: 30, upload_mbps: 10, active_connections: 3 };
  const nodes = [{ group: "FREE" as const, quality: 90, latest }, { group: "INTERMEDIATE" as const, quality: 70, latest }];
  assert.deepEqual(selectionSummary(nodes).active, { value: 3, covered: 1, total: 1 });
  assert.equal(selectionSummary(nodes).rating.value, 80);
  assert.equal(selectionSummary(nodes).download.covered, 2);
  assert.deepEqual(selectionSummary(nodes.slice(1)).active, { value: null, covered: 0, total: 0 });
});
