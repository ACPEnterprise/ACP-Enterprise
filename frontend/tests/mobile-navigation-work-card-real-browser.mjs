import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [baseUrl, credentialPath, receiptPath, outputPath, phase = "after", mode = "enforce"] = process.argv.slice(2);
if (!baseUrl || !credentialPath || !receiptPath || !outputPath) {
  throw new Error("usage: node mobile-navigation-work-card-real-browser.mjs BASE_URL CREDENTIALS RECEIPT OUTPUT [PHASE] [enforce|observe]");
}
if ((statSync(credentialPath).mode & 0o077) !== 0) throw new Error("credential file must use mode 0600");

const credentials = JSON.parse(readFileSync(credentialPath, "utf8"));
const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
const artifactDirectory = `${outputPath}.artifacts`;
mkdirSync(artifactDirectory, { recursive: true, mode: 0o700 });
const profile = mkdtempSync(join(tmpdir(), "om1b-mobile-card-browser-"));
const debuggingPort = Number(process.env.OM1B_CHROME_DEBUG_PORT ?? "19341");
const chrome = spawn(
  process.env.OM1B_CHROME_EXECUTABLE ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--remote-allow-origins=*",
    `--remote-debugging-port=${debuggingPort}`,
    `--user-data-dir=${profile}`,
    "about:blank",
  ],
  { stdio: "ignore" },
);

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
async function eventually(callback, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      return await callback();
    } catch (error) {
      lastError = error;
      await delay(150);
    }
  }
  throw lastError ?? new Error("browser condition timed out");
}

let socket;
let sequence = 0;
const pending = new Map();
function command(method, params = {}) {
  const id = ++sequence;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
async function evaluate(expression) {
  const response = await command("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text);
  return response.result?.value;
}
async function navigate(path) {
  await command("Page.navigate", { url: new URL(path, baseUrl).toString() });
  await eventually(async () => {
    const value = await evaluate("document.readyState");
    if (value !== "complete") throw new Error(`page is ${value}`);
  });
  await eventually(async () => {
    if (!(await evaluate("Boolean(document.querySelector('.theme-shell'))"))) throw new Error("application shell unavailable");
  });
}
async function setViewport(viewport) {
  await command("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: viewport.mobile ? 3 : 1,
    mobile: viewport.mobile,
    screenWidth: viewport.width,
    screenHeight: viewport.height,
  });
}
async function setTheme(theme) {
  await evaluate(`(() => {
    const select = document.querySelector('select[aria-label="Theme preference"]');
    if (!select) throw new Error('theme control unavailable');
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
    setter.call(select, ${JSON.stringify(theme)});
    select.dispatchEvent(new Event('change', { bubbles: true }));
  })()`);
  await eventually(async () => {
    if ((await evaluate("document.documentElement.dataset.theme")) !== theme) throw new Error("theme did not change");
  });
}
async function screenshot(name) {
  const capture = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const bytes = Buffer.from(capture.data, "base64");
  const path = join(artifactDirectory, `${name}.png`);
  writeFileSync(path, bytes, { mode: 0o600 });
  return { name, path, bytes: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") };
}

const viewports = [
  { name: "w320", width: 320, height: 568, mobile: true },
  { name: "w375", width: 375, height: 812, mobile: true },
  { name: "w390", width: 390, height: 844, mobile: true },
  { name: "w414", width: 414, height: 896, mobile: true },
  { name: "w430", width: 430, height: 932, mobile: true },
  { name: "w768", width: 768, height: 1024, mobile: true },
  { name: "iphone-landscape", width: 844, height: 390, mobile: true },
  { name: "w1024", width: 1024, height: 768, mobile: false },
  { name: "desktop", width: 1440, height: 1000, mobile: false },
];
const routes = [
  { name: "company-setup", path: "/onboarding" },
  { name: "customers", path: "/customers" },
  ...(receipt.job_id ? [{ name: "job-details", path: `/jobs/${encodeURIComponent(receipt.job_id)}` }] : []),
  { name: "csr", path: "/scheduling" },
  { name: "dispatch", path: "/dispatch" },
  { name: "accounting", path: "/accounting" },
  { name: "employees", path: "/employees" },
  { name: "payroll", path: "/payroll" },
];
const themes = ["light", "dark"];
const findings = [];
const artifacts = [];

try {
  const target = await eventually(async () => {
    const response = await fetch(`http://127.0.0.1:${debuggingPort}/json/list`);
    const targets = await response.json();
    const page = targets.find((item) => item.type === "page");
    if (!page?.webSocketDebuggerUrl) throw new Error("Chrome target unavailable");
    return page;
  });
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
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
  await setViewport(viewports[2]);

  await command("Page.navigate", { url: new URL("/login", baseUrl).toString() });
  await eventually(async () => {
    if (!(await evaluate("Boolean(document.querySelector('#login-email') && document.querySelector('#login-password'))"))) {
      throw new Error("login form unavailable");
    }
  });
  await evaluate(`(() => {
    const set = (selector, value) => {
      const element = document.querySelector(selector);
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(element, value);
      element.dispatchEvent(new Event('input', { bubbles: true }));
    };
    set('#login-email', ${JSON.stringify(credentials.email)});
    set('#login-password', ${JSON.stringify(credentials.password)});
    document.querySelector('form').requestSubmit();
  })()`);
  await eventually(async () => {
    if ((await evaluate("location.pathname")) === "/login") throw new Error("login incomplete");
  });

  for (const viewport of viewports) {
    await setViewport(viewport);
    for (const theme of themes) {
      for (const route of routes) {
        await navigate(route.path);
        await setTheme(theme);
        const observation = await eventually(async () => {
          const value = await evaluate(`(() => {
            const desktop = document.querySelector('.theme-navigation-desktop');
            const content = document.querySelector('.theme-shell-content');
            const trigger = document.querySelector('button[aria-label="Open navigation"]');
            const cards = [...document.querySelectorAll('.twelve-hats-panel-outline, .primary-work-panel, .dashboard-card-border')];
            const probe = document.createElement('span');
            probe.style.color = 'var(--semantic-panel-outline)';
            document.body.append(probe);
            const expectedColor = getComputedStyle(probe).color;
            probe.remove();
            const cardStyles = cards.map((card) => {
              const style = getComputedStyle(card);
              return { width: style.borderTopWidth, style: style.borderTopStyle, color: style.borderTopColor };
            });
            return {
              path: location.pathname,
              viewportWidth: innerWidth,
              documentWidth: document.documentElement.scrollWidth,
              desktopDisplay: desktop ? getComputedStyle(desktop).display : null,
              triggerDisplay: trigger ? getComputedStyle(trigger).display : null,
              content: content ? content.getBoundingClientRect().toJSON() : null,
              expectedColor,
              cardCount: cards.length,
              invalidCards: cardStyles.filter((item) => item.width !== '2px' || item.style !== 'solid' || item.color !== expectedColor),
            };
          })()`);
          if (!value.content) throw new Error("shell content unavailable");
          return value;
        });
        const mobileLayout = viewport.width < 1024;
        const errors = [];
        if (observation.documentWidth > observation.viewportWidth) errors.push("horizontal-overflow");
        if (mobileLayout && observation.desktopDisplay !== "none") errors.push("desktop-sidebar-visible");
        if (mobileLayout && Math.abs(observation.content.left) > 1) errors.push("reserved-sidebar-offset");
        if (mobileLayout && observation.content.width < observation.viewportWidth - 1) errors.push("content-not-full-width");
        if (mobileLayout && observation.triggerDisplay === "none") errors.push("hamburger-hidden");
        if (!mobileLayout && observation.desktopDisplay === "none") errors.push("desktop-sidebar-hidden");
        if (!mobileLayout && observation.triggerDisplay !== "none") errors.push("desktop-hamburger-visible");
        if (observation.cardCount === 0) errors.push("no-work-cards-observed");
        if (observation.invalidCards.length > 0) errors.push("invalid-work-card-border");

        if (mobileLayout) {
          await evaluate("document.querySelector('button[aria-label=\"Open navigation\"]').click()");
          const drawer = await eventually(async () => {
            const value = await evaluate(`(() => {
              const drawer = document.querySelector('#mobile-application-navigation');
              if (!drawer) return null;
              const style = getComputedStyle(drawer);
              return {
                position: style.position,
                left: drawer.getBoundingClientRect().left,
                width: drawer.getBoundingClientRect().width,
                bodyPosition: document.body.style.position,
                bodyOverflow: document.body.style.overflow,
                rootOverflow: document.documentElement.style.overflow,
                links: [...drawer.querySelectorAll('a')].map((item) => item.textContent.trim()),
              };
            })()`);
            if (!value) throw new Error("mobile drawer unavailable");
            return value;
          });
          if (drawer.position !== "fixed" || Math.abs(drawer.left) > 1) errors.push("drawer-not-fixed-overlay");
          if (drawer.width >= observation.viewportWidth) errors.push("drawer-exceeds-viewport");
          if (drawer.bodyPosition !== "fixed" || drawer.bodyOverflow !== "hidden" || drawer.rootOverflow !== "hidden") errors.push("background-scroll-not-locked");
          for (const label of ["Customers", "Dispatch", "Accounting", "Employees", "Payroll"]) {
            if (!drawer.links.includes(label)) errors.push(`authorized-link-missing:${label}`);
          }
          const representative = route.name === (receipt.job_id ? "job-details" : "dispatch")
            && ["w390", "iphone-landscape"].includes(viewport.name);
          if (representative) artifacts.push(await screenshot(`${phase}-${theme}-${viewport.name}-${route.name}-open`));
          await evaluate("document.querySelector('.theme-navigation-backdrop').click()");
          await eventually(async () => {
            if (await evaluate("Boolean(document.querySelector('#mobile-application-navigation'))")) throw new Error("drawer did not close");
          });
          if (viewport.name === "w390" && theme === "light" && route.name === "dispatch") {
            await evaluate("document.querySelector('button[aria-label=\"Open navigation\"]').click()");
            await eventually(async () => {
              if (!(await evaluate("Boolean(document.querySelector('#mobile-application-navigation'))"))) throw new Error("drawer unavailable for close-control check");
            });
            await evaluate("document.querySelector('#mobile-application-navigation button[aria-label=\"Close navigation\"]').click()");
            await eventually(async () => {
              if (await evaluate("Boolean(document.querySelector('#mobile-application-navigation'))")) throw new Error("close control did not close drawer");
            });

            await evaluate("document.querySelector('button[aria-label=\"Open navigation\"]').click()");
            await evaluate("window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))");
            await eventually(async () => {
              if (await evaluate("Boolean(document.querySelector('#mobile-application-navigation'))")) throw new Error("Escape did not close drawer");
            });

            await evaluate("document.querySelector('button[aria-label=\"Open navigation\"]').click()");
            await eventually(async () => {
              if (!(await evaluate("Boolean(document.querySelector('#mobile-application-navigation'))"))) throw new Error("drawer unavailable for destination check");
            });
            await evaluate("document.querySelector('#mobile-application-navigation a[href=\"/customers\"]').click()");
            await eventually(async () => {
              const state = await evaluate("({ path: location.pathname, drawer: Boolean(document.querySelector('#mobile-application-navigation')) })");
              if (state.path !== "/customers" || state.drawer) throw new Error("destination did not navigate and close drawer");
            });
            await navigate(route.path);
            await setTheme(theme);
          }
        } else if (route.name === (receipt.job_id ? "job-details" : "dispatch") && viewport.name === "desktop") {
          artifacts.push(await screenshot(`${phase}-${theme}-${viewport.name}-${route.name}`));
        }
        findings.push({ viewport: viewport.name, width: viewport.width, height: viewport.height, theme, route: route.name, path: route.path, card_count: observation.cardCount, errors });
      }
    }
  }

  const failures = findings.filter((finding) => finding.errors.length > 0);
  const output = {
    schema: "twelvehats.om1b.mobile-navigation-work-card-browser.v1",
    phase,
    mode,
    serving_sha: process.env.OM1B_SERVING_SHA ?? null,
    fixture: "SYNTHETIC_ISOLATED",
    authenticated: true,
    actual_browser: true,
    viewports,
    routes,
    themes,
    findings,
    artifacts,
    failures: failures.length,
    protected_acceptance: false,
  };
  writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, { mode: 0o600 });
  if (mode === "enforce" && failures.length > 0) throw new Error(`${failures.length} responsive/card browser checks failed`);
  console.log(JSON.stringify({ status: failures.length ? "FAIL" : "PASS", checks: findings.length, artifacts: artifacts.length, output: outputPath }));
} finally {
  socket?.close();
  chrome.kill("SIGTERM");
  await delay(300);
  rmSync(profile, { recursive: true, force: true });
}
