import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { createServer } from "node:net";
import { startAdminPreview } from "./admin-preview.mjs";

const root = resolve(import.meta.dirname, "..", "..");
const backendURL = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8000";
const adminCLI = resolve(root, "scripts", "e2e", "admin-preview.mjs");
const playwrightCLI = resolve(root, "node_modules", "@playwright", "test", "cli.js");
const ownedServices = [];

for (const requiredPath of [adminCLI, playwrightCLI]) {
  if (!existsSync(requiredPath)) {
    throw new Error(`Required E2E runtime file is missing: ${requiredPath}. Build and install the workspace first.`);
  }
}

async function isAvailable(url, expectedContentType) {
  try {
    const response = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(1_000) });
    if (!response.ok) return false;
    const contentType = response.headers.get("content-type") ?? "";
    return !expectedContentType || expectedContentType.test(contentType);
  } catch {
    return false;
  }
}

function startService(name, args, cwd, env) {
  const child = spawn(process.execPath, args, {
    cwd,
    env: { ...process.env, ...env },
    shell: false,
    stdio: "inherit",
    windowsHide: true,
  });
  ownedServices.push({ name, child });
  return child;
}

async function waitForService(name, url, child, expectedContentType) {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    if (await isAvailable(url, expectedContentType)) return;
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`${name} exited before becoming available.`);
    }
    await new Promise((resolveDelay) => setTimeout(resolveDelay, 250));
  }
  throw new Error(`${name} did not become available within 120 seconds.`);
}

async function ensureService(name, url, args, cwd, env, expectedContentType) {
  await new Promise((done, reject) => {
    const probe = createServer();
    probe.once("error", () => reject(new Error(`${name} port is occupied; stop the existing service explicitly.`)));
    probe.listen(Number(new URL(url).port), "127.0.0.1", () => probe.close(done));
  });
  let child;
  if (name === "Admin production Nginx") {
    const service = startAdminPreview();
    ownedServices.push(service);
    child = service.child;
  } else {
    child = startService(name, args, cwd, env);
  }
  await waitForService(name, url, child, expectedContentType);
}

async function waitForExit(child, timeoutMs) {
  if (child.exitCode !== null || child.signalCode !== null) return true;
  return new Promise((resolveExit) => {
    const timer = setTimeout(() => resolveExit(false), timeoutMs);
    child.once("exit", () => {
      clearTimeout(timer);
      resolveExit(true);
    });
  });
}

async function stopService({ child, cleanup: cleanupOwnedContainer }) {
  cleanupOwnedContainer?.();
  if (child.exitCode !== null || child.signalCode !== null) return;
  child.kill();
  if (await waitForExit(child, 5_000)) return;
  if (process.platform === "win32" && child.pid) {
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], {
      shell: false,
      stdio: "ignore",
      timeout: 5_000,
      windowsHide: true,
    });
  } else {
    child.kill("SIGKILL");
  }
  await waitForExit(child, 5_000);
}

let cleanupPromise;
function cleanup() {
  cleanupPromise ??= Promise.all(ownedServices.toReversed().map(stopService));
  return cleanupPromise;
}

let runner;
let interrupted = false;
async function interrupt() {
  if (interrupted) return;
  interrupted = true;
  runner?.kill();
  await cleanup();
  process.exit(130);
}

process.once("SIGINT", interrupt);
process.once("SIGTERM", interrupt);

try {
  await ensureService(
    "Admin production Nginx",
    "http://127.0.0.1:3001/umi.js",
    [adminCLI],
    resolve(root, "apps", "admin"),
    { E2E_BACKEND_URL: backendURL },
    /javascript/i,
  );

  runner = spawn(process.execPath, [playwrightCLI, "test", ...process.argv.slice(2)], {
    cwd: root,
    env: { ...process.env, E2E_MANAGED_SERVERS: "1" },
    shell: false,
    stdio: "inherit",
    windowsHide: true,
  });
  const runnerCode = await new Promise((resolveExit) => {
    runner.once("exit", (code) => resolveExit(code ?? 1));
    runner.once("error", () => resolveExit(1));
  });
  process.exitCode = runnerCode;
} finally {
  await cleanup();
}
