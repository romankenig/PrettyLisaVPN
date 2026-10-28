import test from "node:test";
import assert from "node:assert/strict";
import { groupSummaries, nodeGroup } from "../src/groups.ts";

test("group summaries include empty groups and weight known hours, not server averages", () => {
  const base = { available: true, latest: { active_connections: 2 } };
  const result = groupSummaries([
    { ...base, group: "INTERMEDIATE", known_hours: 10, successful_hours: 10 },
    { ...base, group: "FREE", known_hours: 9, successful_hours: 9 },
    { ...base, available: false, group: "FREE", known_hours: 1, successful_hours: 0 },
  ]);
  assert.deepEqual(result[1], { group: "FREE", servers: 2, available: 1, active: 4, availability: 90 });
  assert.deepEqual(result[2], { group: "PREMIUM", servers: 0, available: 0, active: 0, availability: null });
  assert.equal(nodeGroup({ group: "INTERMEDIATE", is_available_for_free: false }), "INTERMEDIATE");
});
