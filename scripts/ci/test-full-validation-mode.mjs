import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { stripTypeScriptTypes } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { runInNewContext } from "node:vm";
import YAML from "yaml";

const root = path.resolve(import.meta.dirname, "../..");
const read = (file) => readFileSync(path.join(root, file), "utf8");
const workflow = YAML.parse(read(".github/workflows/ci-e2e.yml"), { merge: true });
const { source, frontend, backend, "full-validation": validation } = workflow.jobs;
const find = (job, name) => {
  const step = job.steps.find((candidate) => candidate.name === name);
  assert(step, `Missing step: ${name}`);
  return step;
};
const modeOutput = "${{ needs.source.outputs.validation_mode }}";
const modeCondition = (mode) => `\${{ needs.source.outputs.validation_mode == '${mode}' }}`;

assert.deepEqual(Object.keys(workflow.on), ["workflow_dispatch"]);
assert.deepEqual(workflow.on.workflow_dispatch.inputs.validation_mode, {
  description: workflow.on.workflow_dispatch.inputs.validation_mode.description,
  required: true, default: "full", type: "choice", options: ["full", "smoke"],
});
assert(workflow["run-name"].includes("inputs.validation_mode"));
assert(workflow.concurrency.group.includes("inputs.validation_mode"));
assert.equal(source.outputs.validation_mode, "${{ steps.input.outputs.validation_mode }}");
assert.deepEqual(frontend.strategy.matrix.app, ["admin"]);
assert.deepEqual(validation.needs, ["source", "backend", "frontend"]);
assert.equal(frontend.needs, "source");
assert.equal(backend.needs, "source");

const unit = find(frontend, "Run frontend unit tests");
assert.equal(unit.if, modeCondition("full"));
assert(unit.run.includes('pnpm --filter "@pinjie/$APP" test'));
const skipped = find(frontend, "Record skipped frontend unit tests");
assert.equal(skipped.if, modeCondition("smoke"));
assert(skipped.run.includes("Vitest and coverage skipped"));
assert(frontend.steps.some((step) => step.run?.includes('build pnpm --filter "@pinjie/$APP" build')));
assert(find(backend, "Run Backend pytest").run.endsWith("uv run pytest"));
const e2e = find(validation, "Run browser E2E");
assert.equal(e2e.id, "e2e");
assert.equal(e2e.env.E2E_PROFILE, modeOutput);
assert(e2e.run.endsWith("pnpm test:e2e"));

// Only intentional mode gates and diagnostics may be conditional. Required jobs,
// builds, pytest, production restore and E2E must not silently skip or ignore errors.
const conditionalSteps = new Set([
  unit, skipped,
  ...["full", "smoke"].flatMap((mode) => [
    find(validation, `Write ${mode} validation evidence`),
    find(validation, `Upload ${mode} validation evidence`),
  ]),
]);
for (const job of Object.values(workflow.jobs)) {
  assert(!Object.hasOwn(job, "if"), "Required jobs cannot be conditional.");
  assert(!Object.hasOwn(job, "continue-on-error"));
  for (const step of job.steps) {
    assert(!Object.hasOwn(step, "continue-on-error"), "Validation cannot ignore step failures.");
    if (Object.hasOwn(step, "if") && !conditionalSteps.has(step)) {
      assert.equal(step.if, "${{ always() }}");
      assert(step.name.startsWith("Save ") && step.uses?.startsWith("actions/upload-artifact@"));
    }
  }
}

for (const mode of ["full", "smoke"]) {
  const writer = find(validation, `Write ${mode} validation evidence`);
  const upload = find(validation, `Upload ${mode} validation evidence`);
  assert.equal(writer.id, `${mode}-evidence`);
  assert.equal(writer.if,
    `\${{ success() && needs.source.outputs.validation_mode == '${mode}' && steps.e2e.outcome == 'success' }}`);
  assert.equal(upload.if,
    `\${{ success() && needs.source.outputs.validation_mode == '${mode}' && steps.${mode}-evidence.outcome == 'success' }}`);
  assert.equal(upload.with.name, `${mode}-validation-\${{ needs.source.outputs.commit_sha }}`);
  assert.equal(upload.with.path, `\${{ runner.temp }}/${mode}-validation-evidence/${mode}-validation.env`);
  assert.equal(upload.with["if-no-files-found"], "error");
}

// Evaluate the real config and registration hooks with inert fixtures. This does
// not invoke Playwright, any browser, application, database or business journey.
function scriptSource(file) {
  return stripTypeScriptTypes(read(file)).replace(/^import[\s\S]*?;\s*/gmu, "");
}
const configSource = scriptSource("playwright.config.ts")
  .replace("export default defineConfig", "globalThis.config = defineConfig");
const expectedProjects = ["admin-desktop", "admin-mobile"];
for (const profile of [undefined, "full", "smoke", "fast", "", "FULL"]) {
  const context = {
    process: { env: profile === undefined ? {} : { E2E_PROFILE: profile } },
    defineConfig: (value) => value,
    devices: { "Desktop Chrome": {}, "Pixel 7": {} },
  };
  if (profile !== undefined && !["full", "smoke"].includes(profile)) {
    assert.throws(() => runInNewContext(configSource, context), /Unsupported E2E_PROFILE/);
    continue;
  }
  runInNewContext(configSource, context);
  assert.deepEqual(Array.from(context.config.projects, (project) => project.name), expectedProjects);
  for (const projectName of expectedProjects) {
    for (const file of ["e2e/stage-c.spec.ts", "e2e/system-status.spec.ts"]) {
      const hooks = [];
      const cases = [];
      const skip = Symbol("skipped");
      const reachedPage = Symbol("reached-page");
      const test = (name, callback) => cases.push({ name, callback });
      test.describe = (_name, callback) => callback();
      test.beforeEach = (callback) => hooks.push(callback);
      test.info = () => ({ project: { name: projectName } });
      test.skip = (condition) => { if (condition) throw skip; };
      runInNewContext(scriptSource(file), {
        test, Buffer, process: context.process,
        uniqueUsername: () => "fixture-user",
      });
      assert.equal(cases.length, 2, `${file} must retain both application journeys.`);
      let runnable = 0;
      for (const { callback } of cases) {
        try {
          for (const hook of hooks) await hook({}, test.info());
          await callback({ page: {
            on: () => {},
            goto: () => { throw reachedPage; },
          } });
          assert.fail("Expected the journey to reach page navigation or explicitly skip.");
        } catch (error) {
          if (error === reachedPage) runnable++;
          else if (error !== skip) throw error;
        }
      }
      const mobileStageC = file.endsWith("stage-c.spec.ts") && projectName.endsWith("-mobile");
      assert.equal(runnable, profile === "smoke" && mobileStageC ? 0 : 1,
        `${profile ?? "default"}/${projectName}/${file}: unexpected validation scope`);
    }
  }
}

const gitExecutable = process.platform === "win32"
  ? spawnSync("where.exe", ["git.exe"], { encoding: "utf8" }).stdout?.split(/\r?\n/u).find(Boolean)
  : undefined;
if (process.platform === "win32") assert(gitExecutable, "Git for Windows is required.");
const bash = gitExecutable ? path.join(path.dirname(path.dirname(gitExecutable)), "bin/bash.exe") : "bash";
const shellPath = (value) => value.replaceAll("\\", "/").replace(/^([A-Za-z]):/u, (_, drive) => `/${drive.toLowerCase()}`);
const temporary = mkdtempSync(path.join(tmpdir(), "pinjie-validation-mode-"));
const sha = "a".repeat(40);
const runId = "987654321";
function runBash(script, env) {
  return spawnSync(bash, ["-e", "-o", "pipefail", "-c", script], {
    encoding: "utf8", timeout: 10_000, windowsHide: true, env: { ...process.env, ...env },
  });
}
const input = find(source, "Validate immutable input");
assert.equal(input.env.VALIDATION_MODE, "${{ inputs.validation_mode }}");
try {
  for (const mode of ["full", "smoke", "fast", "", "FULL"]) {
    const output = path.join(temporary, `output-${mode || "empty"}`);
    const result = runBash(input.run, {
      COMMIT_SHA: sha, VALIDATION_MODE: mode, DEFAULT_BRANCH: "main",
      GITHUB_REF: "refs/heads/main", GITHUB_OUTPUT: shellPath(output),
    });
    if (["full", "smoke"].includes(mode)) {
      assert.equal(result.status, 0, result.stderr);
      assert(readFileSync(output, "utf8").includes(`validation_mode=${mode}\n`));
    } else assert.notEqual(result.status, 0, `Input must reject ${JSON.stringify(mode)}.`);
  }
  // Execute the actual evidence writers and pass both outputs through the real
  // strict consumer. Filename and forged-field cases have separate PS fixtures.
  for (const mode of ["full", "smoke"]) {
    const result = runBash(find(validation, `Write ${mode} validation evidence`).run, {
      RUNNER_TEMP: shellPath(temporary), COMMIT_SHA: sha,
      GITHUB_RUN_ID: runId, GITHUB_RUN_ATTEMPT: "1",
    });
    assert.equal(result.status, 0, result.stderr);
    const manifest = path.join(temporary, `${mode}-validation-evidence`, `${mode}-validation.env`);
    const content = readFileSync(manifest, "utf8");
    assert(content.includes(`schema=pinjie-mall-${mode}-validation-v1\n`));
    if (mode === "smoke") {
      for (const field of ["frontend_unit_tests=skipped", "browser=playwright-chromium-smoke",
        "e2e_scope=all-quality-pages,desktop-stage-c", "backend=pytest"]) assert(content.includes(`${field}\n`));
    }
    const checked = spawnSync(process.platform === "win32" ? "powershell.exe" : "pwsh", [
      "-NoLogo", "-NoProfile", "-File", path.join(root, "scripts/ci/check-full-validation-evidence.ps1"),
      "-ManifestPath", manifest, "-ExpectedCommitSha", sha, "-ExpectedRunId", runId,
    ], { encoding: "utf8", timeout: 10_000, windowsHide: true });
    assert.ifError(checked.error);
    if (mode === "full") assert.equal(checked.status, 0, checked.stderr);
    else assert.notEqual(checked.status, 0, "Strict must reject the actual smoke evidence.");
  }
} finally {
  assert.equal(path.dirname(temporary), path.resolve(tmpdir()));
  assert(path.basename(temporary).startsWith("pinjie-validation-mode-"));
  rmSync(temporary, { recursive: true, force: true });
}

console.log("Validation mode guards passed: input rejection, required steps, full/smoke scope, real evidence writers and strict isolation; no browsers or application tests executed.");
