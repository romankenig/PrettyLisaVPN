/* eslint @typescript-eslint/no-require-imports: "off" */
/* global process, require, console */
const fs = require("node:fs");
const { spawnSync } = require("node:child_process");
const base = process.env.FORMAT_BASE || "origin/develop";
const diff = spawnSync("git", ["diff", "--name-only", base, "HEAD"], {
  encoding: "utf8",
});
if (diff.status !== 0) throw new Error(diff.stderr);
const files = diff.stdout
  .split(/\r?\n/)
  .filter(
    (file) =>
      /^apps\/windows\//.test(file) &&
      /\.(tsx?|css|json|cjs)$/.test(file) &&
      fs.existsSync("../../" + file),
  )
  .map((file) => file.replace(/^apps\/windows\//, ""));
if (!files.length) process.exit(0);
const result = spawnSync("pnpm", ["exec", "prettier", "--check", ...files], {
  stdio: "inherit",
});
if (result.status === 0) process.exit(0);
const formatted = spawnSync("pnpm", ["exec", "prettier", "--write", ...files], {
  stdio: "inherit",
});
if (formatted.status !== 0) process.exit(1);
fs.mkdirSync("artifacts/formatting", { recursive: true });
fs.writeFileSync(
  "artifacts/formatting/suggestions.json",
  JSON.stringify(
    files.map((file) => ({
      path: "apps/windows/" + file,
      content: fs.readFileSync(file, "utf8"),
    })),
  ),
);
console.error(
  "Formatting suggestions uploaded; commit them before this check can pass.",
);
process.exit(1);
