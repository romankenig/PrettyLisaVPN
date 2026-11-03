import { releaseBlockers } from "../src/model.mjs";
const blockers = releaseBlockers();
for (const blocker of blockers) console.error(`BLOCKED: ${blocker}`);
console.error(
  "Informational website publication is authorized. Commercial checkout still requires a separately reviewed rollout.",
);
process.exitCode = 1;
