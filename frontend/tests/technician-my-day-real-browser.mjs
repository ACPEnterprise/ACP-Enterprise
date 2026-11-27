import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [baseUrl, credentialPath, receiptPath, outputPath, phase] = process.argv.slice(2);
if (!baseUrl || !credentialPath || !receiptPath || !outputPath || !phase) {
  throw new Error("usage: node technician-my-day-real-browser.mjs BASE_URL CREDENTIALS RECEIPT OUTPUT PHASE");
}
if ((statSync(credentialPath).mode & 0o077) !== 0) {
  throw new Error("credential file must use mode 0600");
}

const credentials = JSON.parse(readFileSync(credentialPath, "utf8"));
const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
const artifactsDirectory = `${outputPath}.artifacts`;
mkdirSync(artifactsDirectory, { recursive: true, mode: 0o700 });
const profile = mkdtempSync(join(tmpdir(), "om1b-technician-browser-"));
const debuggingPort = Number(process.env.OM1B_CHROME_DEBUG_PORT ?? "19331");
const chrome = spawn(
  process.env.OM1B_CHROME_EXECUTABLE
    ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
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
  });
}
async function screenshot(name) {
  const capture = await command("Page.captureScreenshot", {
    format: "png",
    captureBeyondViewport: false,
  });
  const bytes = Buffer.from(capture.data, "base64");
  const path = join(artifactsDirectory, `${name}.png`);
  writeFileSync(path, bytes, { mode: 0o600 });
  return {
    path,
    bytes: bytes.length,
    sha256: createHash("sha256").update(bytes).digest("hex"),
  };
}

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
  await command("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });

  await navigate("/login");
  await eventually(async () => {
    const ready = await evaluate(
      "Boolean(document.querySelector('#login-email') && document.querySelector('#login-password'))",
    );
    if (!ready) throw new Error("login form unavailable");
  });
  await evaluate(`(() => {
    const set = (selector, value) => {
      const element = document.querySelector(selector);
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      setter.call(element, value);
      element.dispatchEvent(new Event("input", { bubbles: true }));
    };
    set("#login-email", ${JSON.stringify(credentials.email)});
    set("#login-password", ${JSON.stringify(credentials.password)});
    document.querySelector("form").requestSubmit();
  })()`);
  await eventually(async () => {
    if ((await evaluate("location.pathname")) === "/login") {
      throw new Error("authenticated navigation has not completed");
    }
  });

  await navigate("/technician");
  const body = await eventually(async () => {
    const text = await evaluate("document.body.innerText");
    for (const expected of [
      "My day",
      receipt.technician_display_name,
      receipt.customer_display_name,
      receipt.appointment_number,
      receipt.job_number,
    ]) {
      if (!text.includes(expected)) throw new Error(`My Day is missing ${expected}`);
    }
    if (text.includes("No assigned visits")) throw new Error("My Day is empty");
    return text;
  });
  const artifact = await screenshot(`${phase}-technician-my-day`);
  const output = {
    schema: "twelvehats.om1b.technician-my-day-browser.v1",
    phase,
    serving_sha: process.env.OM1B_SERVING_SHA,
    fixture: "SYNTHETIC_DISPOSABLE",
    authenticated: true,
    independent_browser_profile: true,
    rendered_path: await evaluate("location.pathname"),
    assertions: {
      technician_visible: body.includes(receipt.technician_display_name),
      assigned_customer_visible: body.includes(receipt.customer_display_name),
      appointment_visible: body.includes(receipt.appointment_number),
      job_visible: body.includes(receipt.job_number),
      empty_state_absent: !body.includes("No assigned visits"),
    },
    artifact,
  };
  writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, { mode: 0o600 });
  console.log(JSON.stringify({ status: "PASS", phase, output: outputPath }));
} finally {
  socket?.close();
  chrome.kill("SIGTERM");
  await delay(300);
  rmSync(profile, { recursive: true, force: true });
}
