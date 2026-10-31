/* eslint @typescript-eslint/no-require-imports: "off" */
/* global process, console, window, localStorage, setTimeout, require */
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { spawn, spawnSync } = require("node:child_process");
const { chromium } = require("playwright-core");
const output = path.resolve("artifacts/managed-acceptance");
fs.mkdirSync(output, { recursive: true });
const account = JSON.parse(
  fs.readFileSync(process.env.ACCEPTANCE_CREDENTIAL_PATH, "utf8"),
);
const families = new Map([
  ["wireguard", "WireGuard"],
  ["amneziawg", "Amnezia"],
  ["sstp", "SSTP"],
  ["softether", "SoftEther"],
  ["shadowsocks2022", "SS2022"],
  ["vmess", "VMess"],
  ["vless", "VLESS"],
  ["vless_reality", "REALITY"],
  ["hysteria", "Hysteria"],
  ["hysteria2", "Hysteria 2"],
  ["hysteria2_salamander", "Salamander"],
]);
if (
  !["DE", "US"].includes(account.country) ||
  !account.methods?.length ||
  !account.methods.every((id) => families.has(id.replace(/_relay$/, "")))
)
  throw new Error("Invalid acceptance matrix");
const modes = account.routing_modes || ["all"];
if (
  !modes.length ||
  !modes.every((m) => ["all", "include", "exclude"].includes(m))
)
  throw new Error("Invalid routing matrix");
const origins = [
  "https://api.ipify.org",
  "https://ipv4.icanhazip.com",
  "https://ifconfig.me/ip",
];
function ip(origin, tunnel = false) {
  const probe = spawnSync(
    "curl.exe",
    [
      "--silent",
      "--fail",
      "--max-time",
      "20",
      "-4",
      ...(tunnel ? ["--interface", "172.30.255.1"] : []),
      origin,
    ],
    { encoding: "utf8", timeout: 25000 },
  );
  if (
    probe.status !== 0 ||
    !/^[0-9]{1,3}(\.[0-9]{1,3}){3}$/.test(probe.stdout.trim())
  )
    throw new Error("Diagnostic origin unavailable");
  return probe.stdout.trim();
}
const baseline = modes.some((m) => m !== "all")
  ? origins.map((origin) => ip(origin))
  : [];
const exits = account.expected_egress_ips || [];
if (
  baseline.length &&
  (!exits.length || baseline.some((value) => exits.includes(value)))
)
  throw new Error("Diagnostic routes are not independent");
const report = {
  source_sha: process.env.GITHUB_SHA,
  run: process.env.GITHUB_RUN_ID,
  attempt: process.env.GITHUB_RUN_ATTEMPT,
  country: account.country,
  results: [],
};
const save = () =>
  fs.writeFileSync(
    path.join(output, "proof.json"),
    JSON.stringify(report, null, 2),
  );
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let app, browser, page;
async function connectWebView() {
  for (let i = 0; i < 120; i++) {
    try {
      browser = await chromium.connectOverCDP("http://127.0.0.1:9222");
      break;
    } catch {
      await delay(500);
    }
  }
  if (!browser) throw new Error("WebView unavailable");
  for (let i = 0; i < 60; i++) {
    page = browser
      .contexts()
      .flatMap((c) => c.pages())
      .find((p) => /(?:tauri\.localhost|localhost)/.test(p.url()));
    if (page) break;
    await delay(500);
  }
  if (!page) throw new Error("Native page unavailable");
  page.setDefaultTimeout(30000);
}
async function nativeUp() {
  return page.evaluate(() => window.__TAURI_INTERNALS__.invoke("engine_is_up"));
}
async function capture(method) {
  const result = spawnSync(
    "pwsh",
    [
      "-NoProfile",
      "-File",
      path.resolve("scripts/ci/capture-native-window.ps1"),
      "-AppProcessId",
      String(app.pid),
      "-OutputPath",
      path.join(output, method + ".png"),
      "-Action",
      "Capture",
    ],
    { encoding: "utf8", timeout: 60000 },
  );
  if (result.error || result.status)
    throw new Error("Native screenshot failed");
}
async function main() {
  try {
    app = spawn(
      path.resolve("src-tauri/target/release/prettylisavpn-windows.exe"),
      [],
      {
        env: {
          ...process.env,
          WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:
            "--remote-debugging-port=9222 --disable-gpu",
          WEBVIEW2_USER_DATA_FOLDER: fs.mkdtempSync(
            path.join(os.tmpdir(), "prettylisa-managed-"),
          ),
        },
        stdio: "ignore",
      },
    );
    await connectWebView();
    await page.locator("#login-email").waitFor();
    await page.evaluate(async (credential) => {
      await window.__TAURI_INTERNALS__.invoke("save_refresh_credential", {
        credential,
      });
    }, account.credential);
    for (const [method, mode] of account.methods.flatMap((method) =>
      modes.map((mode) => [method, mode]),
    )) {
      await page.evaluate(
        ({ userId, country, method, mode }) => {
          const list = {
            services: [
              {
                id: "11111111-1111-4111-8111-111111111111",
                slug: "telegram",
                name: "Telegram",
                icon: "telegram",
                domains: ["telegram.org", "*.telegram.org"],
                ipv4_cidrs: ["149.154.160.0/20"],
              },
            ],
            masks: ["api.ipify.org", "ifconfig.me"],
          };
          localStorage.setItem(
            "prettylisavpn:traffic:v1",
            JSON.stringify({ mode, include: list, exclude: list }),
          );
          localStorage.setItem("prettylisavpn:language", "en");
          localStorage.setItem(
            "prettylisavpn:enabled-vpn-methods:v1",
            JSON.stringify([method]),
          );
          localStorage.setItem(
            `prettylisavpn.location.${userId}`,
            JSON.stringify({ mode: "COUNTRY", country_code: country }),
          );
        },
        { userId: account.userId, country: account.country, method, mode },
      );
      await page.reload();
      await page.getByText(account.email, { exact: true }).waitFor();
      await page.locator(".location-trigger").waitFor();
      // Home restores/cleans the previous session asynchronously after sign-in.
      // A click during RECONCILING is intentionally ignored by the controller.
      await page.waitForFunction(
        () =>
          window.document
            .querySelector(".connection-status")
            ?.textContent?.trim() === "Not connected",
      );
      const row = {
        method,
        routing_mode: mode,
        split_verified: mode === "all",
        connected: false,
        tunnel_https: false,
        cleanup: false,
      };
      report.results.push(row);
      save();
      try {
        const start = Date.now();
        await page.locator(".connection-card > button").click();
        let started = false;
        while (Date.now() - start < 180000) {
          if (await page.locator(".connection-attempt").count()) started = true;
          if (await page.locator(".connection-info").count()) {
            row.connected = true;
            break;
          }
          if (started && (await page.locator(".connection-error").count()))
            break;
          await delay(250);
        }
        row.connect_seconds = Math.floor((Date.now() - start) / 1000);
        if (row.connected) {
          const expected =
            families.get(method.replace(/_relay$/, "")) +
            (method.endsWith("_relay") ? "+" : "");
          await page.waitForFunction(
            (expected) =>
              window.document
                .querySelector(".connection-info p")
                ?.textContent?.startsWith(expected),
            expected,
          );
          const sustained = Date.now();
          while (
            Date.now() - sustained < 40000 &&
            (await page.locator(".connection-info").count())
          )
            await delay(500);
          row.sustained_seconds = Math.floor((Date.now() - sustained) / 1000);
          row.native_up = await nativeUp();
          // Independent HTTPS request explicitly bound to the real Wintun address.
          const probe = spawnSync(
            "curl.exe",
            [
              "--silent",
              "--fail",
              "--max-time",
              "15",
              "--interface",
              "172.30.255.1",
              "https://api.prettylisavpn.com/health",
            ],
            { encoding: "utf8", timeout: 20000 },
          );
          row.tunnel_https =
            probe.status === 0 && /"status"\s*:\s*"ok"/.test(probe.stdout);
          if (mode !== "all") {
            try {
              const actual = origins.map((origin, index) => {
                try {
                  return ip(origin, true);
                } catch {
                  row[`origin_${index}_error`] = "PROBE_FAILED";
                  throw new Error("PROBE_FAILED");
                }
              });
              const location = await page.evaluate(() =>
                window.__TAURI_INTERNALS__.invoke("get_vpn_location"),
              );
              row.vpn_location_verified =
                location.ip === actual[2] && exits.includes(location.ip);
              if (!row.vpn_location_verified)
                throw new Error("LOCATION_FAILED");
              const pageProbe = spawnSync(
                "curl.exe",
                [
                  "--silent",
                  "--fail",
                  "--max-time",
                  "20",
                  "-4",
                  "--interface",
                  "172.30.255.1",
                  "--user-agent",
                  "Mozilla/5.0 PrettyLisaVPN-Acceptance",
                  "https://ifconfig.me/",
                ],
                { encoding: "utf8", timeout: 25000 },
              );
              row.ifconfig_page =
                pageProbe.status === 0 && pageProbe.stdout.includes(actual[2]);
              if (!row.ifconfig_page) throw new Error("PAGE_FAILED");
              row.split_verified = actual.every((value, index) => {
                const vpn =
                  index === 2 || (index !== 1) === (mode === "include");
                return vpn ? exits.includes(value) : value === baseline[index];
              });
            } catch {
              row.split_verified = false;
            }
          }
          await capture(method + "-" + mode);
        } else {
          // Stable error codes only; never export profiles, tokens or network logs.
          const text = await page
            .locator(".connection-error")
            .allTextContents();
          row.codes = text.join(" ").match(/\b[A-Z][A-Z_]{3,}\b/g) || [];
          await capture(method + "-" + mode);
        }
      } finally {
        const button = page.locator(".connection-card > button");
        if (
          (await page
            .locator(".connection-info, .connection-attempt")
            .count()) ||
          (await nativeUp())
        )
          await button.click();
        const until = Date.now() + 60000;
        while (
          Date.now() < until &&
          ((await page
            .locator(".connection-info, .connection-attempt")
            .count()) ||
            (await nativeUp()) ||
            (await button.isDisabled()))
        )
          await delay(250);
        row.cleanup =
          !(await nativeUp()) &&
          !(await page
            .locator(".connection-info, .connection-attempt")
            .count()) &&
          !(await button.isDisabled());
        save();
      }
      if (!row.cleanup)
        throw new Error("Cleanup unconfirmed; remaining methods stopped");
    }
    if (
      !report.results.every(
        (r) =>
          r.split_verified &&
          r.connected &&
          r.native_up &&
          r.tunnel_https &&
          r.cleanup &&
          r.sustained_seconds >= 40,
      )
    )
      throw new Error("Real method matrix failed; inspect redacted proof");
    console.log(
      "Real packaged managed tunnels: verification, HTTPS, renewal and cleanup passed",
    );
  } finally {
    save();
    if (page && !report.results.length)
      await capture("startup").catch(() => {});
    if (page)
      await page
        .evaluate(() => window.__TAURI_INTERNALS__.invoke("engine_stop"))
        .catch(() => {});
    if (browser) await browser.close().catch(() => {});
    if (app) app.kill();
  }
}
main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
