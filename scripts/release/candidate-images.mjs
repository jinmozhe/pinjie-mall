import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { resolve, posix } from "node:path";
import YAML from "yaml";
import { apps, hash, idPattern, imageVariables, repository, requireCondition, validateRequest } from "./composition.mjs";
import { run, trustedHandoff } from "./github-evidence.mjs";

requireCondition(process.env.GITHUB_ACTIONS === "true" && process.env.GITHUB_REPOSITORY === repository &&
  idPattern.test(process.env.GITHUB_RUN_ID ?? "") && idPattern.test(process.env.GITHUB_RUN_ATTEMPT ?? "") &&
  process.env.RUNNER_TEMP && !process.env.DOCKER_HOST && !process.env.DOCKER_CONTEXT,
"Candidate validation requires this repository's isolated GitHub runner and local Docker daemon.");
const project = `pinjie-candidate-${process.env.GITHUB_RUN_ID}-${process.env.GITHUB_RUN_ATTEMPT}`;
const runtime = resolve(process.env.RUNNER_TEMP, project);
const output = resolve(process.env.RUNNER_TEMP, "candidate-evidence");
const composeFile = resolve(runtime, "compose.json");
const composeArgs = ["compose", "--project-name", project, "--env-file", resolve(runtime, "empty.env"), "--file", composeFile];

function cleanup() {
  if (existsSync(composeFile)) {
    run("docker", [...composeArgs, "down", "--volumes", "--remove-orphans", "--timeout", "10"], { timeout: 90_000 });
  }
  if (existsSync(runtime)) rmSync(runtime, { recursive: true, force: true });
}

if (process.argv[2] === "cleanup") {
  cleanup();
} else {
  requireCondition(process.argv[2] === "validate", "Use validate or cleanup.");
  requireCondition(!existsSync(runtime) && !existsSync(output), "Candidate runtime or output already exists; use a fresh attempt.");
  mkdirSync(runtime);
  mkdirSync(output);
  const started = Date.now();
  let success = false;
  let phase = "source-evidence";
  try {
    const request = validateRequest(JSON.parse(process.env.CANDIDATE_REQUEST_JSON ?? ""));
    const branch = process.env.DEFAULT_BRANCH;
    requireCondition(process.env.GITHUB_REF === `refs/heads/${branch}`, "Dispatch from the default branch.");
    requireCondition(run("git", ["rev-parse", "HEAD"]) === request.test_commit, "Checkout must match the requested test source.");
    run("git", ["merge-base", "--is-ancestor", request.test_commit, `origin/${branch}`]);
    const routing = YAML.parse(readFileSync(".cnb.yml", "utf8"), { merge: true }).main.push;
    const handoffs = {};
    for (const app of apps) {
      const image = request.images[app];
      const source = image.release.source.commit_sha;
      run("git", ["merge-base", "--is-ancestor", source, request.test_commit]);
      const changed = run("git", ["diff", "--name-only", "-z", source, request.test_commit]).split("\0").filter(Boolean);
      requireCondition(!changed.some((file) => routing[`${app}-image`].ifModify.some((pattern) => posix.matchesGlob(file, pattern))),
        `${app}: source changes require rebuilding this image at the test commit.`);
      const evidencePath = resolve(runtime, `${app}-release.json`);
      writeFileSync(evidencePath, `${JSON.stringify(image.release)}\n`);
      run(process.execPath, ["scripts/ci/check-cnb-release-evidence.mjs", "--manifest", evidencePath,
        "--expected-image", app, "--expected-commit", source, "--expected-build-id", image.release.cnb.build_id]);
      handoffs[app] = trustedHandoff(image, branch, resolve(runtime, `${app}-handoff`));
      const ref = image.release.image.reference;
      const tag = `${ref.split("@")[0]}:sha-${source}`;
      const { spawnSync } = await import("node:child_process");
      const raw = spawnSync("docker", ["buildx", "imagetools", "inspect", tag, "--raw"], { timeout: 120_000, maxBuffer: 8 * 1024 * 1024 });
      requireCondition(!raw.error && raw.status === 0, `${app}: registry tag inspection failed.`);
      const index = JSON.parse(raw.stdout);
      // Buildx may append a newline to the raw manifest. Resolve the descriptor digest directly.
      const descriptor = JSON.parse(run("docker", ["buildx", "imagetools", "inspect", tag, "--format", "{{json .Manifest}}"]));
      requireCondition(descriptor.digest === image.release.image.digest, `${app}: immutable tag differs from candidate digest.`);
      requireCondition(index.manifests?.some((entry) => entry.annotations?.["vnd.docker.reference.type"] === "attestation-manifest"),
        `${app}: BuildKit attestation is missing.`);
      run("docker", ["pull", "--platform", "linux/amd64", ref], { timeout: 20 * 60_000 });
      const inspected = JSON.parse(run("docker", ["image", "inspect", ref]))[0];
      requireCondition(inspected.Architecture === "amd64" && inspected.Os === "linux" &&
        inspected.Config.Labels?.["org.opencontainers.image.revision"] === source &&
        inspected.Config.Labels?.["org.opencontainers.image.source"] === `https://github.com/${repository}`,
        `${app}: pulled image platform or source labels differ.`);
    }
    phase = "isolated-runtime";
    const secret = () => randomBytes(32).toString("hex");
    const databasePassword = secret();
    const adminPassword = secret();
    const databaseURL = `postgresql+asyncpg://postgres:${databasePassword}@postgres:5432/pinjie_candidate_test`;
    const environment = {
      ENVIRONMENT: "test", DATABASE_URL: databaseURL, TEST_DATABASE_URL: databaseURL,
      REDIS_MODE: "required", REDIS_URL: "redis://redis:6379/0", TEST_REDIS_URL: "redis://redis:6379/0",
      WEB_ORIGINS: '["https://miniapp.invalid"]', ADMIN_ORIGINS: '["http://127.0.0.1:3001"]',
      TRUSTED_HOSTS: '["backend","localhost","127.0.0.1"]', API_DOCS_ENABLED: "false", LOG_FILE_ENABLED: "false",
      WEB_JWT_SECRET: secret(), ADMIN_JWT_SECRET: secret(), WEB_TOKEN_HMAC_KEY: secret(), ADMIN_TOKEN_HMAC_KEY: secret(),
      INITIAL_ADMIN_PASSWORD: adminPassword, UPLOAD_LOCAL_ROOT: "/app/storage/uploads", SETTINGS_MEDIA_ROOT: "/app/storage/settings-media",
    };
    const config = {
      services: {
        postgres: { image: "postgres:18.4-alpine", environment: { POSTGRES_PASSWORD: databasePassword, POSTGRES_DB: "pinjie_candidate_test" },
          healthcheck: { test: ["CMD-SHELL", "pg_isready -U postgres -d pinjie_candidate_test"], interval: "2s", timeout: "2s", retries: 30 } },
        redis: { image: "redis:8.10.0-alpine", healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: "2s", timeout: "2s", retries: 30 } },
        backend: { image: request.images.backend.release.image.reference, platform: "linux/amd64", environment,
          ports: ["127.0.0.1:18168:18168"], depends_on: { postgres: { condition: "service_healthy" }, redis: { condition: "service_healthy" } } },
        admin: { image: request.images.admin.release.image.reference, platform: "linux/amd64", ports: ["127.0.0.1:3001:3001"],
          depends_on: { backend: { condition: "service_healthy" } } },
      },
    };
    writeFileSync(resolve(runtime, "empty.env"), "", { mode: 0o600 });
    writeFileSync(composeFile, JSON.stringify(config), { mode: 0o600 });
    run("docker", [...composeArgs, "up", "-d", "--wait", "--wait-timeout", "120", "postgres", "redis"], { timeout: 300_000 });
    for (const command of [
      ["alembic", "upgrade", "head"],
      ["python", "-m", "scripts.set_test_registration", "--enabled", "--confirm-database", "pinjie_candidate_test"],
      ["python", "-m", "scripts.sync_permissions", "--apply", "--confirm-database", "pinjie_candidate_test"],
      ["python", "-m", "scripts.create_initial_admin", "--username", "stage-admin", "--confirm-database", "pinjie_candidate_test"],
    ]) run("docker", [...composeArgs, "run", "--rm", "--no-deps", "backend", ...command], { timeout: 180_000 });
    run("docker", [...composeArgs, "up", "-d", "--wait", "--wait-timeout", "180", "backend", "admin"], { timeout: 300_000 });
    phase = "playwright";
    run(process.execPath, ["node_modules/@playwright/test/cli.js", "test"], { timeout: 20 * 60_000,
      env: { ...process.env, E2E_MANAGED_SERVERS: "1", E2E_ADMIN_USERNAME: "stage-admin", E2E_ADMIN_PASSWORD: adminPassword,
        E2E_SUMMARY_DIR: output }, stdio: ["ignore", "pipe", "pipe"] });
    const browser = JSON.parse(readFileSync(resolve(output, "e2e-summary.json"), "utf8"));
    requireCondition(browser.status === "passed" && Array.isArray(browser.tests) &&
      ["admin-desktop", "admin-mobile"].every((project) =>
        browser.tests.some((test) => test.project === project && test.status === "passed")),
    "Browser evidence must include passing tests in both Admin desktop/mobile projects.");
    phase = "cleanup";
    cleanup();
    const manifest = { schema: "pinjie-mall-deployment-composition-v1", request, request_sha256: hash(request), handoffs,
      validation: { status: "passed", run_id: process.env.GITHUB_RUN_ID, run_attempt: process.env.GITHUB_RUN_ATTEMPT,
        workflow_commit: process.env.GITHUB_SHA, tested_at: new Date().toISOString(),
        scope: "linux-amd64-postgres-redis-production-images-playwright" } };
    writeFileSync(resolve(output, "deployment-composition.json"), `${JSON.stringify(manifest, null, 2)}\n`);
    writeFileSync(resolve(output, "images.env"), `${Object.entries(imageVariables(request)).map(([key, value]) => `${key}=${value}`).join("\n")}\n`);
    success = true;
  } finally {
    if (!success) {
      for (const file of ["deployment-composition.json", "images.env"]) rmSync(resolve(output, file), { force: true });
    }
    writeFileSync(resolve(output, "candidate-summary.json"), `${JSON.stringify({ phase, success, duration_ms: Date.now() - started })}\n`);
    cleanup();
  }
}
