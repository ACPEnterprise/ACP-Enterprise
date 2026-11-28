import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [baseUrl, credentialPath, receiptPath, outputPath, phase = "initial"] = process.argv.slice(2);
if (!baseUrl || !credentialPath || !receiptPath || !outputPath) {
  throw new Error("usage: node real-browser-workflow.mjs BASE_URL CREDENTIALS RECEIPT OUTPUT [PHASE]");
}

if ((statSync(credentialPath).mode & 0o077) !== 0) {
  throw new Error("credential file must not be accessible by group or other users (mode 0600 required)");
}

const credentials = JSON.parse(readFileSync(credentialPath, "utf8"));
const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
const artifactDirectory = `${outputPath}.artifacts`;
mkdirSync(artifactDirectory, { recursive: true, mode: 0o700 });
const profile = mkdtempSync(join(tmpdir(), "om2b-chrome-"));
const debuggingPort = Number(process.env.OM2B_CHROME_DEBUG_PORT ?? "19222");
const browserExecutable = process.env.OM2B_CHROME_EXECUTABLE
  ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const servingSha = process.env.OM2B_SERVING_SHA;
if (!servingSha) {
  throw new Error("OM2B_SERVING_SHA is required and must identify the code served by the runtime");
}
const chrome = spawn(
  browserExecutable,
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
      await delay(200);
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
  const response = await command("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.text);
  return response.result?.value;
}

async function navigate(path) {
  await command("Page.navigate", { url: new URL(path, baseUrl).toString() });
  await eventually(async () => {
    const state = await evaluate("document.readyState");
    if (state !== "complete") throw new Error(`page is ${state}`);
    return state;
  });
}

async function screenshot(name) {
  const capture = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  const bytes = Buffer.from(capture.data, "base64");
  const path = join(artifactDirectory, `${name}.png`);
  writeFileSync(path, bytes, { mode: 0o600 });
  return { name, sha256: createHash("sha256").update(bytes).digest("hex"), bytes: bytes.length };
}

try {
  const target = await eventually(async () => {
    const response = await fetch(`http://127.0.0.1:${debuggingPort}/json/list`);
    const targets = await response.json();
    const page = targets.find((item) => item.type === "page");
    if (!page?.webSocketDebuggerUrl) throw new Error("Chrome page target unavailable");
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
  const setViewport = (viewport) => command("Emulation.setDeviceMetricsOverride", {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile: viewport.mobile ?? false,
  });
  await setViewport({ width: 1440, height: 1000 });

  await navigate("/login");
  await eventually(async () => {
    const ready = await evaluate("Boolean(document.querySelector('#login-email') && document.querySelector('#login-password'))");
    if (!ready) throw new Error("login form unavailable");
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
    const location = await evaluate("location.pathname");
    if (location === "/login") throw new Error("login has not completed");
  });

  const revenue = receipt.revenue_cycle;
  const checks = process.env.QBO_HISTORICAL_ACCEPTANCE === "true"
    ? [{
      name: "qbo-historical-accounting",
      path: "/financial-reports",
      viewport: { width: 1440, height: 1000 },
      expected: [
        "Complete QuickBooks historical archive",
        "20,702",
        "97,093",
        "46,405",
        "Unresolved financial exceptions",
      ],
    }]
    : process.env.REVENUE_CYCLE_ACCEPTANCE === "true"
      ? [
        {
          name: "estimate-desktop",
          path: `/estimates?id=${revenue.estimate_id}`,
          viewport: { width: 1440, height: 1000 },
          expected: [revenue.estimate_number, "Synthetic leak diagnostic — revised", "approved", "Immutable revision 2", "Total"],
        },
        {
          name: "invoice-tablet",
          path: `/invoices/${revenue.invoice_id}`,
          viewport: { width: 820, height: 1180 },
          expected: [revenue.invoice_number, "Office payment history", "Cash", "Check", "settlement not confirmed"],
        },
        {
          name: "revenue-cycle-mobile",
          path: "/revenue-cycle",
          viewport: { width: 390, height: 844, mobile: true },
          expected: ["Revenue cycle", "Open Invoices", "Payment receipts"],
        },
      ]
    : [
      { name: "customer", path: `/customers/${receipt.customer_id}`, viewport: { width: 1440, height: 1000 }, expected: ["Integration Acceptance", "History completeness", "Service locations"] },
      { name: "job", path: `/jobs/${receipt.job_id}`, viewport: { width: 1440, height: 1000 }, expected: ["Integration acceptance service request", "Customer", "Service Location", "Appointments"] },
      { name: "scheduling", path: "/scheduling", viewport: { width: 1440, height: 1000 }, expected: ["Schedule", "Appointments"] },
      { name: "dispatch", path: "/dispatch", viewport: { width: 1440, height: 1000 }, expected: ["Schedule", "Appointments"] },
      { name: "employees", path: "/employees", viewport: { width: 1440, height: 1000 }, expected: ["Employees"] },
      { name: "price-book", path: "/price-book", viewport: { width: 1440, height: 1000 }, expected: ["Price Book"] },
      { name: "estimates", path: "/estimates", viewport: { width: 1440, height: 1000 }, expected: ["Estimates"] },
      { name: "invoices", path: "/invoices", viewport: { width: 1440, height: 1000 }, expected: ["Invoices"] },
    ];
  const results = [];
  const artifacts = [];
  for (const check of checks) {
    await setViewport(check.viewport);
    await navigate(check.path);
    if (check.name === "qbo-historical-accounting") {
      await eventually(async () => {
        const opened = await evaluate(`(() => {
          const details = document.querySelector('details');
          if (!details) return false;
          if (!details.open) details.querySelector('summary')?.click();
          return details.open;
        })()`);
        if (!opened) throw new Error("accounting source-evidence drawer unavailable");
      });
    }
    const body = await eventually(async () => {
      const text = await evaluate("document.body.innerText");
      const missing = check.expected.filter((value) => !text.includes(value));
      if (missing.length > 0) {
        throw new Error(`${check.name} missing expected operator text: ${missing.join(", ")}`);
      }
      return text;
    }, check.name === "qbo-historical-accounting" ? 60_000 : 20_000);
    const location = await evaluate("location.pathname + location.search");
    artifacts.push(await screenshot(`${phase}-${check.name}`));
    results.push({ name: check.name, requested_path: check.path, rendered_path: location, expected_text: check.expected, text_length: body.length, status: "PASS" });
  }
  const output = {
    schema: "twelvehats.om2b.real-browser-workflow.v1",
    phase,
    browser: process.env.OM2B_BROWSER_LABEL ?? "Chromium-compatible browser",
    base_url: baseUrl,
    serving_sha: servingSha,
    fixture: process.env.QBO_HISTORICAL_ACCEPTANCE === "true"
      ? "ISOLATED_QBO_HISTORICAL_CUSTODY"
      : process.env.REVENUE_CYCLE_ACCEPTANCE === "true"
        ? "SYNTHETIC_REVENUE_CYCLE_DISPOSABLE"
        : "SYNTHETIC_DISPOSABLE",
    authenticated: true,
    results,
    artifacts,
    all_county_operational_acceptance: false,
  };
  writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, { mode: 0o600 });
  console.log(JSON.stringify({ status: "PASS", phase, checks: results.length, output: outputPath }));
} finally {
  socket?.close();
  chrome.kill("SIGTERM");
  await delay(300);
  rmSync(profile, { recursive: true, force: true });
}
