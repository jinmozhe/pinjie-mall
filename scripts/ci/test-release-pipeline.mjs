import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import childProcess, { spawnSync } from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import YAML from "yaml";
import { filterScan } from "./cnb-check-scan-evidence.mjs";
import { apps, hash, imageVariables, validateComposition, validateHandoff, validateRequest } from "../release/composition.mjs";
import { deploymentVariables, retentionPlan } from "../release/release-tools.mjs";
import { run } from "../release/github-evidence.mjs";

const originalSpawnSync = childProcess.spawnSync;
try {
  childProcess.spawnSync = (_command, _args, options) => {
    assert.equal(options.shell, false);
    assert.equal(options.windowsHide, true);
    assert.equal(options.timeout, 1234);
    return { status: 0, stdout: "fixture" };
  };
  syncBuiltinESMExports();
  assert.equal(run("git", ["status"], { shell: true, windowsHide: false, timeout: 1234 }), "fixture");
  assert.throws(() => run("unsupported-command", []), /Unsupported release subprocess/u);
} finally {
  childProcess.spawnSync = originalSpawnSync;
  syncBuiltinESMExports();
}

const sha = "a".repeat(40);
const source = { commit_sha: sha, commit_epoch: 1788652800, commit_time: "2026-09-06T00:00:00Z" };
const request = { schema: "pinjie-mall-candidate-request-v1", test_commit: sha,
  images: Object.fromEntries(apps.map((app, index) => [app, { handoff_run_id: "123", release: {
    schema: "pinjie-cnb-tcr-image-v1", image_key: app, source,
    registry: "ccr.ccs.tencentyun.com", namespace: "pinjie-mall",
    cnb: { repository: "pjwl/pinjie-mall", branch: "main", pipeline: `${app}-image`, build_id: "88",
      build_url: "https://cnb.cool/pjwl/pinjie-mall/-/build/88", started_at: source.commit_time, finished_at: source.commit_time },
    image: { reference: `ccr.ccs.tencentyun.com/pinjie-mall/pinjie-mall-${app}@sha256:${String(index + 1).repeat(64)}`,
      repository: `pinjie-mall-${app}`, trivy: "passed", sbom: "cyclonedx-json", provenance: "buildkit-max",
      oci: { revision: sha, created: source.commit_time, source: "https://github.com/jinmozhe/pinjie-mall" },
      digest: `sha256:${String(index + 1).repeat(64)}`, immutable_tag: `sha-${sha}` },
  } }])) };
const handoff = { schema: "pinjie-source-handoff-v1", commit_sha: sha, mode: "strict", reason: "", full_validation_run_id: "100",
  run_id: "123", run_attempt: "1" };
const composition = { schema: "pinjie-mall-deployment-composition-v1", request, request_sha256: hash(request),
  validation: { status: "passed", run_id: "456", run_attempt: "1", workflow_commit: sha,
    tested_at: "2026-09-06T00:00:00Z", scope: "linux-amd64-postgres-redis-production-images-playwright" },
  handoffs: Object.fromEntries(apps.map((app) => [app, handoff])) };
const mutate = (value, change) => { const copy = structuredClone(value); change(copy); return copy; };
assert.equal(validateRequest(request), request);
assert.equal(validateComposition(composition), composition);
for (const change of [
  (r) => { r.images.admin.release.image.reference = "nginx:latest"; },
  (r) => { r.images.admin.release.image.reference += `@${r.images.admin.release.image.digest}`; },
  (r) => { r.images.backend.release.image.digest = `sha256:${"0".repeat(64)}`; },
  (r) => { r.images.backend.handoff_run_id = "$(command)"; },
  (r) => { r.web_public_origin = "https://user:secret@example.com"; },
  (r) => { delete r.images.admin; },
]) assert.throws(() => validateRequest(mutate(request, change)));
assert.throws(() => validateComposition(mutate(composition, (m) => { m.request.test_commit = "b".repeat(40); })));
assert.throws(() => validateComposition(mutate(composition, (m) => { m.validation.status = "skipped"; })));
assert.throws(() => validateHandoff({ ...handoff, mode: "fast", reason: "", full_validation_run_id: "" }, sha, "123", 1));
assert.throws(() => validateHandoff(handoff, sha, "124", 1));
assert.throws(() => validateHandoff(handoff, sha, "123", 2));
validateHandoff({ ...handoff, mode: "fast", reason: "explicit scoped release", full_validation_run_id: "" }, sha, "123", 1);
const envText = Object.entries(imageVariables(request)).map(([k, v]) => `${k}=${v}`).join("\n");
assert.deepEqual(deploymentVariables(envText), imageVariables(request));
assert.throws(() => deploymentVariables(`${envText}\nWEB_PUBLIC_ORIGIN=https://other.example.com`));
assert.throws(() => deploymentVariables(envText.replace(/@sha256:[1-9]+/u, ":latest")));

const inventory = { schema: "pinjie-tcr-inventory-v1", captured_at: "2026-09-06T00:00:00Z",
  tags: apps.map((app) => ({ app, tag: `sha-${sha}`, digest: request.images[app].release.image.digest, created_at: "2026-01-01T00:00:00Z" })) };
inventory.tags.push({ app: "backend", tag: "candidate-old", digest: `sha256:${"f".repeat(64)}`, created_at: "2026-01-01T00:00:00Z" });
inventory.tags.push({ app: "backend", tag: "buildcache-main", digest: `sha256:${"e".repeat(64)}`, created_at: "2026-01-01T00:00:00Z" });
const now = Date.parse(inventory.captured_at);
const retained = retentionPlan(inventory, [composition, composition], now);
assert.equal(retained.review.length, 1);
assert.equal(retained.review[0].tag, "candidate-old");
assert.equal(retained.keep.length, 3);
assert.throws(() => retentionPlan(inventory, [], now));
assert.throws(() => retentionPlan(inventory, [composition, composition], now + 86400_000));
assert.throws(() => retentionPlan(mutate(inventory, (i) => i.tags.shift()), [composition, composition], now));
assert.throws(() => retentionPlan(mutate(inventory, (i) => i.tags.push(i.tags[0])), [composition, composition], now));

const report = { SchemaVersion: 2, ArtifactType: "container_image", Results: [{ Target: "alpine", Class: "os-pkgs",
  Packages: [{ Name: "openssl" }], Vulnerabilities: [
    { VulnerabilityID: "CVE-2099-0001", Severity: "HIGH", FixedVersion: "1.2" },
    { VulnerabilityID: "CVE-2099-0002", Severity: "CRITICAL" },
    { VulnerabilityID: "CVE-2099-0003", Severity: "LOW", FixedVersion: "1.3" },
  ] }] };
assert.equal(filterScan(report).Results[0].Vulnerabilities.length, 1);
assert.equal(report.Results[0].Vulnerabilities.length, 3);
for (const invalid of [{}, { ...report, Results: [] }, mutate(report, (r) => { r.Results[0].Packages = []; }),
  mutate(report, (r) => { r.Results[0].Vulnerabilities[0].Severity = "invalid"; })]) assert.throws(() => filterScan(invalid));

const full = YAML.parse(readFileSync(".github/workflows/ci-e2e.yml", "utf8"));
assert.deepEqual(Object.keys(full.on), ["workflow_dispatch"]);
assert.deepEqual(full.jobs.frontend.strategy.matrix.app, ["admin"]);
assert.deepEqual(full.jobs["full-validation"].needs, ["source", "backend", "frontend"]);
assert.equal(full.jobs.backend.needs, "source");
assert.equal(full.jobs.frontend.needs, "source");
const candidate = YAML.parse(readFileSync(".github/workflows/validate-candidate-images.yml", "utf8"));
assert.deepEqual(Object.keys(candidate.on), ["workflow_dispatch"]);
assert.equal(candidate.jobs.validate.environment, "candidate-image-validation");
assert.equal(candidate.jobs.validate.steps.find((s) => s.name === "Upload validated deployment composition").if, "${{ success() }}");
const cnb = YAML.parse(readFileSync(".cnb.yml", "utf8"), { merge: true });
const stages = cnb.main.push["backend-image"].stages.map((s) => s.name);
assert(stages.indexOf("Enforce structured vulnerability gate") < stages.indexOf("Publish immutable SHA tag"));
const handoffWorkflow = YAML.parse(readFileSync(".github/workflows/publish-images.yml", "utf8"));
assert.equal(handoffWorkflow.concurrency.group, "cnb-source-handoff-main");
assert(handoffWorkflow.jobs.handoff.steps.some((s) => s.name === "Upload durable handoff evidence"));
for (const mode of ["success", "source-error", "wrong-digest", "stale-app", "browser-error", "partial-browser", "cleanup-error"]) {
  const temporary = mkdtempSync(resolve(tmpdir(), "pinjie-candidate-fixture-"));
  try {
    const result = spawnSync(process.execPath, ["--import", "./scripts/ci/fixtures/candidate-processes.mjs", "scripts/release/candidate-images.mjs", "validate"], {
      encoding: "utf8", timeout: 30_000,
      env: { ...process.env, GITHUB_ACTIONS: "true", GITHUB_REPOSITORY: "jinmozhe/pinjie-mall", GITHUB_REF: "refs/heads/main",
        GITHUB_RUN_ID: "456", GITHUB_RUN_ATTEMPT: "1", GITHUB_SHA: sha, DEFAULT_BRANCH: "main", RUNNER_TEMP: temporary,
        DOCKER_HOST: "", DOCKER_CONTEXT: "", CANDIDATE_REQUEST_JSON: JSON.stringify(request), PINJIE_CANDIDATE_FIXTURE: mode },
    });
    const output = resolve(temporary, "candidate-evidence/deployment-composition.json");
    assert.equal(result.status === 0, mode === "success", `${mode}: ${result.stderr}`);
    assert.equal(existsSync(output), mode === "success", `${mode}: failed runs must not leave deployment evidence`);
    if (mode === "success") {
      const manifest = validateComposition(JSON.parse(readFileSync(output, "utf8")));
      assert.equal(manifest.handoffs.admin.mode, "fast");
      assert.equal(manifest.request_sha256, hash(request));
    }
    if (mode !== "cleanup-error") assert.equal(existsSync(resolve(temporary, "pinjie-candidate-456-1")), false, `${mode}: runtime cleanup`);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}
for (const mode of ["preflight-success", "preflight-tampered", "preflight-failed-run", "preflight-panel-drift"]) {
  const temporary = mkdtempSync(resolve(tmpdir(), "pinjie-preflight-fixture-"));
  try {
    const trusted = mode === "preflight-tampered"
      ? mutate(composition, (m) => { m.validation.tested_at = "2026-09-05T00:00:00Z"; }) : composition;
    writeFileSync(resolve(temporary, "trusted.json"), JSON.stringify(trusted));
    writeFileSync(resolve(temporary, "local.json"), JSON.stringify(composition));
    writeFileSync(resolve(temporary, "images.env"), envText);
    writeFileSync(resolve(temporary, "panel.env"), mode === "preflight-panel-drift" ? envText.replace("sha256:111", "sha256:fff") : envText);
    const result = spawnSync(process.execPath, ["--import", "./scripts/ci/fixtures/candidate-processes.mjs", "scripts/release/release-tools.mjs", "preflight",
      "--manifest", resolve(temporary, "local.json"), "--env-file", resolve(temporary, "images.env"), "--panel-env", resolve(temporary, "panel.env")], {
      encoding: "utf8", timeout: 30_000,
      env: { ...process.env, RUNNER_TEMP: temporary, CANDIDATE_REQUEST_JSON: JSON.stringify(request), PINJIE_CANDIDATE_FIXTURE: mode },
    });
    assert.equal(result.status === 0, mode === "preflight-success", `${mode}: ${result.stderr}`);
    assert(!result.stdout.includes("drift.example.com") && !result.stderr.includes("drift.example.com"));
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}
console.log("Release pipeline fixtures passed: immutable composition, handoff provenance, variable drift, protected retention, scan filtering, and manual workflow gates.");
