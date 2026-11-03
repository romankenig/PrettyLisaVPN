import { mkdir, copyFile, writeFile, cp, rm, lstat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { pages } from "../src/pages.mjs";
import { website, releaseBlockers } from "../src/model.mjs";

export const root = fileURLToPath(new URL("..", import.meta.url));
export const dist = path.join(root, "dist");
export async function build() {
  if (process.env.SITE_RELEASE === "1") {
    const blockers = releaseBlockers();
    if (blockers.length)
      throw new Error(`Publication blocked: ${blockers.join("; ")}`);
    throw new Error(
      "Public payment deployment requires a separately reviewed server integration.",
    );
  }
  // Remove obsolete generated routes; the deletion is confined to this site's dist.
  if (
    path.dirname(dist) !== path.resolve(root) ||
    path.basename(dist) !== "dist"
  )
    throw new Error("Unexpected build directory");
  const previous = await lstat(dist).catch((error) => {
    if (error.code !== "ENOENT") throw error;
  });
  if (previous?.isSymbolicLink())
    throw new Error("Refusing symlink build directory");
  await rm(dist, { recursive: true, force: true });
  await mkdir(path.join(dist, "assets"), { recursive: true });
  await copyFile(
    path.join(root, "public/shop-verification-xO2ZZeK02A.txt"),
    path.join(dist, "shop-verification-xO2ZZeK02A.txt"),
  );
  await writeFile(
    path.join(dist, "build-identity.json"),
    JSON.stringify(
      {
        component: "public-website",
        version: website.version,
        channel: "preview",
        source_sha: process.env.WEBSITE_SOURCE_SHA ?? null,
        run_id: process.env.WEBSITE_BUILD_RUN ?? null,
        run_attempt: process.env.WEBSITE_BUILD_ATTEMPT ?? null,
        deployment: "not-published",
      },
      null,
      2,
    ) + "\n",
  );
  for (const [route, html] of pages()) {
    const target = path.join(dist, route.slice(1), "index.html");
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, html);
  }
  const sources = {
    "lock.svg": "../../apps/windows/src/assets/lock.svg",
    "Rubik.ttf": "../../apps/windows/public/fonts/rubik/Rubik.ttf",
    "OFL.txt": "../../apps/windows/public/fonts/rubik/OFL.txt",
    "app.js": "./src/app.js",
    "downloads.mjs": "./src/downloads.mjs",
    "style.css": "./src/style.css",
  };
  for (const [name, source] of Object.entries(sources))
    await copyFile(path.resolve(root, source), path.join(dist, "assets", name));
  await cp(
    path.join(root, "assets/screenshots"),
    path.join(dist, "assets/screenshots"),
    { recursive: true },
  );
  await writeFile(
    path.join(dist, "robots.txt"),
    "User-agent: *\nDisallow: /\n",
  );
  await writeFile(
    path.join(dist, "_headers"),
    "/*\n  X-Robots-Tag: noindex, nofollow\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: no-referrer\n  Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'\n",
  );
  console.log(`Built ${pages().size} localized pages in ${dist}`);
}
if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
)
  await build();
