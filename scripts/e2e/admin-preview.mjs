import { spawn, spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export function startAdminPreview() {
  const root = resolve(import.meta.dirname, "../..");
  const dist = resolve(root, "apps/admin/dist");
  const config = resolve(root, "apps/admin/nginx.conf");
  if (!existsSync(resolve(dist, "index.html"))) throw new Error("Build Admin before production preview.");
  const backend = new URL(process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18168");
  if (backend.href !== "http://127.0.0.1:18168/") {
    throw new Error("Production Admin preview requires the local Backend on 127.0.0.1:18168.");
  }
  const name = `pinjie-admin-preview-${randomUUID()}`;
  const network = process.platform === "linux"
    ? ["--network", "host", "--add-host", "backend:127.0.0.1"]
    : ["--publish", "127.0.0.1:3001:3001", "--add-host", "backend:host-gateway"];
  const options = { shell: false, windowsHide: true, stdio: "inherit" };
  const create = spawnSync("docker", [
    "create", "--name", name, "--label", `pinjie.test.owner=${name}`, ...network,
    "--mount", `type=bind,source=${dist},target=/usr/share/nginx/html,readonly`,
    "--mount", `type=bind,source=${config},target=/etc/nginx/conf.d/default.conf,readonly`,
    "nginx:1.29-alpine@sha256:5616878291a2eed594aee8db4dade5878cf7edcb475e59193904b198d9b830de",
  ], { ...options, timeout: 180_000 });
  if (create.error || create.status !== 0) throw new Error("Cannot create production Nginx preview.");
  let cleaned = false;
  function cleanup() {
    if (cleaned) return;
    const result = spawnSync("docker", ["rm", "--force", name], { ...options, timeout: 15_000 });
    if (result.error || result.status !== 0) throw new Error(`Cannot remove owned preview container ${name}.`);
    cleaned = true;
  }
  const child = spawn("docker", ["start", "--attach", name], options);
  return { child, cleanup, name: "Admin production Nginx" };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { child, cleanup } = startAdminPreview();
  for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => { cleanup(); process.exitCode = 130; });
  try {
    process.exitCode = await new Promise((done) => {
      child.once("error", () => done(1));
      child.once("exit", (code) => done(code ?? 1));
    });
  } finally {
    cleanup();
  }
}
