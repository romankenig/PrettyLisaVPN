import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { build, dist } from "./build.mjs";

export const headers = {
  "Cache-Control": "no-store",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex, nofollow",
  "Referrer-Policy": "no-referrer",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Content-Security-Policy":
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
};
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ttf": "font/ttf",
  ".txt": "text/plain; charset=utf-8",
  ".json": "application/json; charset=utf-8",
};

export function createPreviewServer() {
  return createServer(async (req, res) => {
    const send = (code, type, body) => {
      res.writeHead(code, { ...headers, "Content-Type": type });
      res.end(req.method === "HEAD" ? undefined : body);
    };
    let pathname;
    try {
      pathname = decodeURIComponent(
        new URL(req.url, "http://127.0.0.1").pathname,
      );
    } catch {
      send(400, "text/plain", "Invalid address");
      return;
    }
    // No provider, credential or billing mutation exists in the preview server.
    if (
      req.method === "POST" &&
      ["/checkout", "/checkout/"].includes(pathname)
    ) {
      res.setHeader("Connection", "close");
      send(
        503,
        "application/json",
        JSON.stringify({ error: { code: "WEB_CHECKOUT_DISABLED" } }),
      );
      return;
    }
    if (!["GET", "HEAD"].includes(req.method)) {
      res.setHeader("Allow", "GET, HEAD");
      send(405, "text/plain", "Method not allowed");
      return;
    }
    if (pathname.includes("\\") || pathname.includes("\0")) {
      send(400, "text/plain", "Invalid address");
      return;
    }
    let target = path.resolve(dist, "." + pathname);
    if (!target.startsWith(dist + path.sep) && target !== dist) {
      send(404, "text/plain", "Not found");
      return;
    }
    try {
      if ((await stat(target)).isDirectory())
        target = path.join(target, "index.html");
      const body = await readFile(target);
      send(
        200,
        types[path.extname(target)] ?? "application/octet-stream",
        body,
      );
    } catch {
      send(
        404,
        "text/html; charset=utf-8",
        await readFile(path.join(dist, "404/index.html")),
      );
    }
  });
}
if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  await build();
  const port = Number(process.env.PORT ?? 4180);
  createPreviewServer().listen(port, "127.0.0.1", () =>
    console.log(`PrettyLisaVPN draft preview: http://127.0.0.1:${port}/`),
  );
}
