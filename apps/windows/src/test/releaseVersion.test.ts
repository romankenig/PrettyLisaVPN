import { expect, it } from "vitest";
import { releaseVersion } from "../ui/releaseVersion";

it.each([
  "0.16.0",
  "0.16.0-dev.40321791718+g177a078abd4f1e60fcba49f8acc849da622939f7",
  "0.16.0-rc.1",
  "0.16.0+build.002",
])("displays the validated release core of %s, like Android", (raw) => {
  expect(releaseVersion(raw)).toBe("0.16.0");
});

it.each([
  "",
  "dev-177a078",
  "0.16",
  "v0.16.0",
  "01.16.0",
  "0.16.0-01",
  "0.16.0+",
  "0.16.0-dev..2",
  "0.16.0 trailing",
  "0.16.0\n",
  "9".repeat(300),
])("does not invent a product version from %s", (raw) => {
  expect(releaseVersion(raw)).toBeNull();
});
