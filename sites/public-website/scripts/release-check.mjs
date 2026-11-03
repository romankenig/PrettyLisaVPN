import { releaseBlockers } from "../src/model.mjs";
const blockers = releaseBlockers();
for (const blocker of blockers) console.error(`BLOCKED: ${blocker}`);
console.error(
  "Preview only. Public publication and payment integration require a separate approved rollout.",
);
process.exitCode = 1;
