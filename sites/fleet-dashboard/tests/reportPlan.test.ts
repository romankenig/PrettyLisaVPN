import { test } from "node:test";
import assert from "node:assert/strict";
import { parseReportPlan, planFromSearch, reportTariffs, selectedPlans, selectionKey, togglePlan, validateReportPlan, withPlan } from "../src/reportPlan.ts";

test("all checkbox subsets round-trip through links without losing other filters", () => {
  for (let mask = 0; mask < 32; mask++) {
    const selected = reportTariffs.filter((_, i) => mask & (1 << i)), key = selectionKey(selected);
    assert.deepEqual(selectedPlans(key), selected);
    const url = withPlan("/dashboard/?period=7d&node_ids=a&node_ids=b&plan=FREE", key);
    assert.equal(planFromSearch(url.split("?")[1]), key);
    assert.deepEqual(new URLSearchParams(url.split("?")[1]).getAll("node_ids"), ["a", "b"]);
    assert.doesNotThrow(() => validateReportPlan({plan: key}, key));
  }
  assert.equal(selectionKey([]), "NONE");
  assert.equal(selectionKey(reportTariffs), "ALL");
});
test("checkboxes can clear, combine and restore all tariffs", () => {
  assert.equal(togglePlan("ALL", "FREE", false), "DEMO,PREMIUM,PLATINUM,UNKNOWN");
  assert.equal(togglePlan("FREE", "FREE", false), "NONE");
  assert.equal(togglePlan("NONE", "FREE", true), "FREE");
  assert.equal(togglePlan("PREMIUM", "FREE", true), "FREE,PREMIUM");
  assert.equal(togglePlan("DEMO,PREMIUM,PLATINUM,UNKNOWN", "FREE", true), "ALL");
});
test("selections normalize duplicates and never accept a response for another set", () => {
  assert.equal(parseReportPlan("PREMIUM,FREE,FREE"), "FREE,PREMIUM");
  assert.equal(planFromSearch("?plan=PREMIUM&plan=FREE"), "FREE,PREMIUM");
  for (const value of ["", "FREE,", "NONE,FREE", "FREE,invalid"]) assert.equal(parseReportPlan(value), null);
  for (const plan of [undefined, "ALL", "FREE", "PREMIUM,FREE"]) assert.throws(() => validateReportPlan({plan}, "FREE,PREMIUM"));
  assert.throws(() => validateReportPlan({}, "NONE"));
});
