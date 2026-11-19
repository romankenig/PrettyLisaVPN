import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const backend =
  process.env.VITE_BACKEND_BASE_URL ?? "https://api.prettylisavpn.com";
if (
  ![
    "https://api.prettylisavpn.com",
    "https://api.test.prettylisavpn.com",
  ].includes(backend)
)
  throw new Error("Invalid build backend");
const website =
  backend === "https://api.test.prettylisavpn.com"
    ? "https://test.prettylisavpn.com"
    : "https://prettylisavpn.com";
const pkg = JSON.parse(readFileSync("package.json", "utf8"));
export default defineConfig({
  base: "./",
  plugins: [
    react(),
    {
      name: "extension-identity",
      closeBundle() {
        const manifest = JSON.parse(readFileSync("dist/manifest.json", "utf8"));
        if (manifest.version !== pkg.version)
          throw new Error("Extension version mismatch");
        manifest.content_security_policy.extension_pages = `script-src 'self'; object-src 'none'; connect-src ${backend} ${website}; base-uri 'none'`;
        writeFileSync("dist/manifest.json", JSON.stringify(manifest, null, 2));
        writeFileSync(
          "dist/build-identity.json",
          JSON.stringify(
            {
              backend,
              version: pkg.version,
              source_sha: process.env.GITHUB_SHA ?? "local",
              run: process.env.GITHUB_RUN_ID ?? "local",
              attempt: process.env.GITHUB_RUN_ATTEMPT ?? "local",
            },
            null,
            2,
          ),
        );
      },
    },
  ],
  build: {
    rollupOptions: {
      input: {
        popup: resolve("popup.html"),
        background: resolve("src/background.ts"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "assets/[name]-[hash].js",
      },
    },
  },
});
