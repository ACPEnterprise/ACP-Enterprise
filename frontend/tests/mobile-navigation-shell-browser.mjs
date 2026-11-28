import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const outputPath = process.argv[2];
if (!outputPath) throw new Error("usage: node tests/mobile-navigation-shell-browser.mjs OUTPUT_JSON");

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const serverPort = Number(process.env.OM1B_MOBILE_VITE_PORT ?? "14179");
const debuggingPort = Number(process.env.OM1B_MOBILE_CDP_PORT ?? "19351");
const baseUrl = `http://127.0.0.1:${serverPort}`;
const browserCandidates = [
  process.env.OM1B_CHROME_EXECUTABLE,
  join(homedir(), "Library/Caches/ms-playwright/chromium_headless_shell-1187/chrome-mac/headless_shell"),
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].filter(Boolean);
const browserExecutable = browserCandidates.find((candidate) => existsSync(candidate));
if (!browserExecutable) throw new Error("No supported Chromium executable is available");
const browserVersionPath = resolve(dirname(browserExecutable), "../VERSION");
const browserVersion = existsSync(browserVersionPath)
  ? readFileSync(browserVersionPath, "utf8").trim()
  : "Chromium (system installation)";

const artifactDirectory = `${outputPath}.artifacts`;
mkdirSync(dirname(resolve(outputPath)), { recursive: true });
mkdirSync(artifactDirectory, { recursive: true });
const browserProfile = mkdtempSync(join(tmpdir(), "om1b-mobile-recovery-browser-"));
const vite = spawn(process.execPath, [
  "node_modules/vite/bin/vite.js",
  "--host", "127.0.0.1",
  "--port", String(serverPort),
  "--strictPort",
], { cwd: frontendRoot, stdio: ["ignore", "pipe", "pipe"] });
const chrome = spawn(browserExecutable, [
  "--headless=new",
  "--disable-gpu",
  "--no-first-run",
  "--no-default-browser-check",
  "--remote-allow-origins=*",
  `--remote-debugging-port=${debuggingPort}`,
  `--user-data-dir=${browserProfile}`,
  "about:blank",
], { stdio: ["ignore", "pipe", "pipe"] });
let viteDiagnostics = "";
let browserDiagnostics = "";
vite.stderr.on("data", (chunk) => { viteDiagnostics = `${viteDiagnostics}${chunk}`.slice(-4000); });
chrome.stderr.on("data", (chunk) => { browserDiagnostics = `${browserDiagnostics}${chunk}`.slice(-4000); });

const delay = (milliseconds) => new Promise((resolvePromise) => setTimeout(resolvePromise, milliseconds));
async function eventually(callback, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return await callback();
    } catch (error) {
      lastError = error;
      await delay(100);
    }
  }
  throw lastError ?? new Error("condition timed out");
}

let socket;
let sequence = 0;
const pending = new Map();
function command(method, params = {}) {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolvePromise, reject) => pending.set(id, { resolve: resolvePromise, reject }));
}
async function evaluate(expression) {
  const response = await command("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text);
  return response.result?.value;
}
async function screenshot(name) {
  const capture = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const bytes = Buffer.from(capture.data, "base64");
  const path = join(artifactDirectory, `${name}.png`);
  writeFileSync(path, bytes);
  return { name, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
}

const viewports = [
  { name: "iphone-se", width: 320, height: 568, mobile: true, insets: { top: 20, right: 0, bottom: 0, left: 0 } },
  { name: "iphone-375", width: 375, height: 812, mobile: true, insets: { top: 47, right: 0, bottom: 34, left: 0 } },
  { name: "iphone-390", width: 390, height: 844, mobile: true, insets: { top: 47, right: 0, bottom: 34, left: 0 } },
  { name: "iphone-414", width: 414, height: 896, mobile: true, insets: { top: 47, right: 0, bottom: 34, left: 0 } },
  { name: "iphone-430", width: 430, height: 932, mobile: true, insets: { top: 59, right: 0, bottom: 34, left: 0 } },
  { name: "iphone-landscape", width: 844, height: 390, mobile: true, insets: { top: 0, right: 47, bottom: 21, left: 47 } },
  { name: "desktop-1024", width: 1024, height: 768, mobile: false, insets: { top: 0, right: 0, bottom: 0, left: 0 } },
  { name: "desktop-1440", width: 1440, height: 1000, mobile: false, insets: { top: 0, right: 0, bottom: 0, left: 0 } },
];
const routes = ["/customers", "/jobs/job-qualification", "/accounting"];
const results = [];
const artifacts = [];
let safeAreaOverrideSupported = true;

try {
  await eventually(async () => {
    if (vite.exitCode !== null) throw new Error(`Vite exited with ${vite.exitCode}: ${viteDiagnostics}`);
    const response = await fetch(`${baseUrl}/tests/fixtures/mobile-navigation-shell.html`);
    if (!response.ok) throw new Error(`Vite returned ${response.status}`);
  });
  const target = await eventually(async () => {
    if (chrome.exitCode !== null) throw new Error(`Chromium exited with ${chrome.exitCode}: ${browserDiagnostics}`);
    const response = await fetch(`http://127.0.0.1:${debuggingPort}/json/list`);
    const targets = await response.json();
    const page = targets.find((item) => item.type === "page");
    if (!page?.webSocketDebuggerUrl) throw new Error("Chromium target unavailable");
    return page;
  });
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolvePromise, reject) => {
    socket.addEventListener("open", resolvePromise, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const waiter = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) waiter.reject(new Error(message.error.message));
    else waiter.resolve(message.result);
  });
  await command("Page.enable");
  await command("Runtime.enable");

  for (const viewport of viewports) {
    await command("Emulation.setDeviceMetricsOverride", {
      width: viewport.width,
      height: viewport.height,
      deviceScaleFactor: viewport.mobile ? 3 : 1,
      mobile: viewport.mobile,
      screenWidth: viewport.width,
      screenHeight: viewport.height,
    });
    await command("Emulation.setTouchEmulationEnabled", { enabled: viewport.mobile, maxTouchPoints: viewport.mobile ? 5 : 1 });
    if (safeAreaOverrideSupported) {
      try {
        await command("Emulation.setSafeAreaInsetsOverride", { insets: viewport.insets });
      } catch {
        safeAreaOverrideSupported = false;
      }
    }

    for (const route of routes) {
      const url = `${baseUrl}/tests/fixtures/mobile-navigation-shell.html?route=${encodeURIComponent(route)}`;
      await command("Page.navigate", { url });
      await eventually(async () => {
        const ready = await evaluate(`Boolean(document.querySelector('.theme-shell') && document.querySelector('[data-current-route=${JSON.stringify(route)}]'))`);
        if (!ready) throw new Error(`shell was not ready for ${route}`);
      });

      const layout = await evaluate(`(() => {
        const desktopNavigation = document.querySelector('.theme-navigation-desktop');
        const content = document.querySelector('.theme-shell-content');
        const trigger = document.querySelector('button[aria-label="Open navigation"]');
        return {
          viewportWidth: innerWidth,
          documentWidth: document.documentElement.scrollWidth,
          desktopDisplay: getComputedStyle(desktopNavigation).display,
          triggerDisplay: getComputedStyle(trigger).display,
          contentLeft: content.getBoundingClientRect().left,
          contentWidth: content.getBoundingClientRect().width,
        };
      })()`);
      const errors = [];
      if (layout.documentWidth > layout.viewportWidth) errors.push("horizontal-overflow");

      if (viewport.mobile) {
        if (layout.desktopDisplay !== "none") errors.push("persistent-sidebar-visible");
        if (layout.triggerDisplay === "none") errors.push("hamburger-hidden");
        if (Math.abs(layout.contentLeft) > 1) errors.push("reserved-sidebar-offset");
        if (layout.contentWidth < layout.viewportWidth - 1) errors.push("content-not-full-width");

        await evaluate("document.querySelector('button[aria-label=\"Open navigation\"]').click()");
        const drawer = await eventually(async () => {
          const value = await evaluate(`(() => {
            const element = document.querySelector('#mobile-application-navigation');
            if (!element) return null;
            const style = getComputedStyle(element);
            const close = element.querySelector('button[aria-label="Close navigation"]');
            return {
              position: style.position,
              left: element.getBoundingClientRect().left,
              paddingTop: parseFloat(style.paddingTop),
              paddingBottom: parseFloat(style.paddingBottom),
              paddingLeft: parseFloat(style.paddingLeft),
              closeTop: close.getBoundingClientRect().top,
              bodyPosition: document.body.style.position,
              bodyOverflow: document.body.style.overflow,
              rootOverflow: document.documentElement.style.overflow,
            };
          })()`);
          if (!value) throw new Error("drawer did not open");
          return value;
        });
        if (drawer.position !== "fixed" || Math.abs(drawer.left) > 1) errors.push("drawer-not-overlay");
        if (drawer.bodyPosition !== "fixed" || drawer.bodyOverflow !== "hidden" || drawer.rootOverflow !== "hidden") errors.push("background-scroll-unlocked");
        if (safeAreaOverrideSupported) {
          if (drawer.paddingTop < viewport.insets.top) errors.push("safe-area-top-missing");
          if (drawer.paddingBottom < viewport.insets.bottom) errors.push("safe-area-bottom-missing");
          if (drawer.paddingLeft < viewport.insets.left) errors.push("safe-area-left-missing");
          if (drawer.closeTop < viewport.insets.top) errors.push("close-control-in-safe-area");
        }
        if (viewport.name === "iphone-390") artifacts.push(await screenshot(`mobile-navigation-${route.slice(1).replaceAll("/", "-")}`));

        const destination = route === "/customers" ? "/jobs" : "/customers";
        await evaluate(`document.querySelector('#mobile-application-navigation a[href=${JSON.stringify(destination)}]').click()`);
        await eventually(async () => {
          const value = await evaluate(`({ drawer: Boolean(document.querySelector('#mobile-application-navigation')), route: document.querySelector('[data-current-route]')?.dataset.currentRoute })`);
          if (value.drawer || value.route !== destination) throw new Error("destination did not close drawer");
        });

        await evaluate("document.querySelector('button[aria-label=\"Open navigation\"]').click()");
        await eventually(async () => {
          if (!(await evaluate("Boolean(document.querySelector('#mobile-application-navigation'))"))) throw new Error("drawer did not reopen");
        });
        await evaluate("document.querySelector('.theme-navigation-backdrop').click()");
        await eventually(async () => {
          if (await evaluate("Boolean(document.querySelector('#mobile-application-navigation'))")) throw new Error("backdrop did not close drawer");
        });
      } else {
        if (layout.desktopDisplay === "none") errors.push("desktop-sidebar-hidden");
        if (layout.triggerDisplay !== "none") errors.push("desktop-hamburger-visible");
      }
      results.push({ viewport: viewport.name, width: viewport.width, height: viewport.height, route, errors });
    }
  }

  const failures = results.filter((result) => result.errors.length > 0);
  const evidence = {
    schema: "twelvehats.om1b.mobile-navigation-regression-recovery.v1",
    baseline_sha: "5d2e46b9db953f41c6cb084949de7537ef060352",
    fixture: "SYNTHETIC_SHELL_ONLY",
    actual_browser: true,
    browser: browserVersion,
    safe_area_override_supported: safeAreaOverrideSupported,
    viewports,
    routes,
    results,
    artifacts,
    failures: failures.length,
    hosted_acceptance: false,
    protected_data_used: false,
  };
  writeFileSync(outputPath, `${JSON.stringify(evidence, null, 2)}\n`);
  if (failures.length) throw new Error(`${failures.length} mobile navigation checks failed`);
  console.log(JSON.stringify({ status: "PASS", checks: results.length, screenshots: artifacts.length, safeAreaOverrideSupported, outputPath }));
} finally {
  socket?.close();
  chrome.kill("SIGTERM");
  vite.kill("SIGTERM");
  await delay(300);
  rmSync(browserProfile, { recursive: true, force: true });
}
