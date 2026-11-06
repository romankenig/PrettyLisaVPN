import test from "node:test";
import assert from "node:assert/strict";
import { availabilityDescription, availabilityFill, combineAvailability, type AvailabilityHour, type AvailabilityStatus } from "../src/availability.ts";

const at = "2026-11-06T10:00:00Z";
const hour = (status: AvailabilityStatus, time = at, checks = 1): AvailabilityHour => ({ at: time, status, checks, modes: ["SYNTHETIC"] });
const node = (...history: AvailabilityHour[]) => ({ history });

test("one failed server occupies only its share, regardless of check frequency", () => {
  const [combined] = combineAvailability([node(hour("HEALTHY", at, 100)), node(hour("HEALTHY")), node(hour("FAILED"))]);
  assert.equal(combined.counts.HEALTHY, 2);
  assert.equal(combined.counts.FAILED, 1);
  assert.equal(combined.checks, 102);
  assert.equal(availabilityFill(combined), "linear-gradient(to top, #51d6ca 0.000% 66.667%, #c82b28 66.667% 100.000%)");
  assert.equal(availabilityDescription(combined), "Доступен: 2 из 3 · Сбой: 1 из 3");
});

test("fully healthy and fully failed selections keep their unambiguous colors", () => {
  assert.equal(availabilityFill(combineAvailability([node(hour("FAILED")), node(hour("FAILED"))])[0]), "#c82b28");
  assert.equal(availabilityFill(combineAvailability([node(hour("HEALTHY"))])[0]), "#51d6ca");
  assert.equal(availabilityFill(hour("FAILED")), undefined);
  assert.equal(availabilityDescription(hour("FAILED")), "Сбой");
});

test("unknown, pending and degraded portions never become a healthy or failed result", () => {
  const [combined] = combineAvailability([node(hour("HEALTHY")), node(hour("UNKNOWN")), node(hour("PENDING")), node(hour("DEGRADED"))]);
  assert.equal(combined.counts.FAILED, 0);
  assert.equal(availabilityFill(combined), "linear-gradient(to top, #51d6ca 0.000% 25.000%, #d7ad0d 25.000% 50.000%, #b7aec9 50.000% 75.000%, #e5def0 75.000% 100.000%)");
  assert.match(availabilityDescription(combined), /Нет подтверждения: 1 из 4/);
});

test("servers not yet registered do not dilute outages or inflate the denominator", () => {
  const [combined] = combineAvailability([node(hour("FAILED")), node(hour("NOT_REGISTERED"))]);
  assert.equal(availabilityFill(combined), "#c82b28");
  assert.equal(availabilityDescription(combined), "Сбой: 1 из 1 · Узел ещё не добавлен: 1");
  const [empty] = combineAvailability([node(hour("NOT_REGISTERED"))]);
  assert.equal(availabilityFill(empty), "#eeeef2");
  assert.equal(availabilityDescription(empty), "Узел ещё не добавлен: 1");
});

test("aligns by timestamp, treats missing hours as unknown and obeys selection", () => {
  const later = "2026-11-06T11:00:00Z";
  const first = node(hour("HEALTHY"), hour("FAILED", later));
  const second = node(hour("HEALTHY", "2026-11-06T11:00:00.000Z"));
  const combined = combineAvailability([first, second]);
  assert.equal(combined.length, 2);
  assert.equal(combined[0].counts.UNKNOWN, 1);
  assert.equal(combined[1].counts.HEALTHY, 1);
  assert.equal(combined[1].counts.FAILED, 1);
  assert.equal(availabilityFill(combineAvailability([second])[0]), "#51d6ca");
  assert.deepEqual(combineAvailability([]), []);
  assert.deepEqual(combineAvailability([node()]), []);
});
