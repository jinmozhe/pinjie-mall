import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import YAML from "yaml";

function requireCondition(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function resolveBashExecutable() {
  if (process.platform !== "win32") {
    return "bash";
  }
  const whereResult = spawnSync("where.exe", ["git.exe"], { encoding: "utf8" });
  const gitExecutable = whereResult.stdout?.split(/\r?\n/u).find(Boolean);
  if (!gitExecutable) {
    throw new Error("Git for Windows is required to run the handoff mode fixtures.");
  }
  return path.join(path.dirname(path.dirname(gitExecutable)), "bin", "bash.exe");
}

function shellPath(value) {
  const normalized = value.replaceAll("\\", "/");
  if (process.platform !== "win32") {
    return normalized;
  }
  return normalized.replace(/^([A-Za-z]):/u, (_, drive) => `/${drive.toLowerCase()}`);
}

function runBash(script, environment) {
  return spawnSync(resolveBashExecutable(), ["-c", script], {
    encoding: "utf8",
    env: { LC_ALL: "C.UTF-8", LANG: "C.UTF-8", ...process.env, ...environment },
  });
}

const workflow = YAML.parse(
  await readFile(new URL("../../.github/workflows/publish-images.yml", import.meta.url), "utf8"),
);
const inputs = workflow.on?.workflow_dispatch?.inputs;
const validateJob = workflow.jobs?.validate;
const validateSteps = validateJob?.steps ?? [];
const stepsByName = new Map(validateSteps.map((step) => [step.name, step]));

requireCondition(inputs && typeof inputs === "object", "Handoff workflow_dispatch inputs are missing.");
requireCondition(
  JSON.stringify(inputs.validation_mode?.options) === JSON.stringify(["strict", "fast"]),
  "validation_mode must offer only strict and fast in that order.",
);
requireCondition(inputs.validation_mode?.type === "choice", "validation_mode must be a choice input.");
requireCondition(inputs.validation_mode?.required === true, "validation_mode must be required.");
requireCondition(inputs.validation_mode?.default === "strict", "validation_mode must default to strict.");
requireCondition(inputs.fast_mode_reason?.type === "string", "fast_mode_reason must be a string input.");
requireCondition(
  inputs.fast_mode_reason?.required === false,
  "fast_mode_reason must be optional at dispatch and conditionally required by validation.",
);
requireCondition(!Object.hasOwn(inputs, "skip_full_validation"), "A skip-by-default boolean is forbidden.");

requireCondition(
  validateJob.outputs?.validation_mode === "${{ steps.release-mode.outputs.validation_mode }}",
  "The validated release mode must be exposed as a job output.",
);

const releaseModeStep = stepsByName.get("Validate release mode");
requireCondition(releaseModeStep?.id === "release-mode", "The release mode validation step is missing.");
requireCondition(!Object.hasOwn(releaseModeStep, "if"), "Release mode validation must always run.");
requireCondition(
  releaseModeStep.run?.includes('case "$VALIDATION_MODE" in') &&
    releaseModeStep.run.includes("strict|fast") &&
    releaseModeStep.run.includes("fast_mode_reason is required") &&
    releaseModeStep.run.includes("fast_mode_reason must contain one line") &&
    releaseModeStep.run.includes("fast_mode_reason must not exceed 200 characters"),
  "Release mode validation must reject unknown modes and invalid fast-mode reasons.",
);

const fullValidationStep = stepsByName.get("Require successful full validation evidence");
requireCondition(fullValidationStep, "The strict Full Validation Artifact step is missing.");
requireCondition(
  fullValidationStep.if === "${{ steps.release-mode.outputs.validation_mode == 'strict' }}",
  "Full Validation Artifact verification must run only in strict mode.",
);
requireCondition(
  fullValidationStep["continue-on-error"] !== true,
  "Strict Full Validation Artifact verification must remain Fail Closed.",
);
requireCondition(
  fullValidationStep.run?.includes("check-full-validation-evidence.ps1"),
  "Strict mode must retain the existing Full Validation evidence guard.",
);

for (const stepName of [
  "Require successful source workflows",
  "Require complete application state",
  "Reject non-ready applications",
  "Validate module boundaries",
]) {
  const step = stepsByName.get(stepName);
  requireCondition(step, `Required handoff guard '${stepName}' is missing.`);
  requireCondition(!Object.hasOwn(step, "if"), `Required handoff guard '${stepName}' must always run.`);
  requireCondition(step["continue-on-error"] !== true, `Required handoff guard '${stepName}' must fail closed.`);
}

const summaryStep = stepsByName.get("Record validation decision");
requireCondition(summaryStep, "The validation decision summary step is missing.");
requireCondition(!Object.hasOwn(summaryStep, "if"), "The validation decision summary must always run.");
requireCondition(
  summaryStep.run?.includes("$GITHUB_STEP_SUMMARY") &&
    summaryStep.run.includes("Full Validation Artifact: verified") &&
    summaryStep.run.includes("Full Validation Artifact: not required by explicit fast mode") &&
    summaryStep.run.includes("FAST_MODE_REASON"),
  "The decision summary must distinguish strict evidence from an explicit fast-mode skip.",
);

const fixtureRoot = mkdtempSync(path.join(os.tmpdir(), "pinjie-cnb-handoff-mode-"));
const githubOutput = path.join(fixtureRoot, "github-output.txt");
const githubSummary = path.join(fixtureRoot, "github-summary.md");

try {
  const runModeValidation = (validationMode, fastModeReason) => {
    writeFileSync(githubOutput, "", "utf8");
    return runBash(releaseModeStep.run, {
      FAST_MODE_REASON: fastModeReason,
      GITHUB_OUTPUT: shellPath(githubOutput),
      VALIDATION_MODE: validationMode,
    });
  };

  for (const [label, validationMode, fastModeReason] of [
    ["strict mode without a reason", "strict", ""],
    ["fast mode with a reason", "fast", "仅调整低风险展示文案"],
  ]) {
    const result = runModeValidation(validationMode, fastModeReason);
    requireCondition(result.status === 0, `Expected ${label} to pass.\n${result.stderr}`);
    requireCondition(
      readFileSync(githubOutput, "utf8").trim() === `validation_mode=${validationMode}`,
      `Expected ${label} to write the validated mode.`,
    );
  }

  for (const [label, validationMode, fastModeReason] of [
    ["an unknown mode", "skip", "reason"],
    ["a missing fast-mode reason", "fast", ""],
    ["a whitespace-only fast-mode reason", "fast", "   \t"],
    ["a multiline fast-mode reason", "fast", "line one\nline two"],
    ["an overlong fast-mode reason", "fast", "x".repeat(201)],
  ]) {
    const result = runModeValidation(validationMode, fastModeReason);
    requireCondition(result.status !== 0, `Expected ${label} to fail.`);
  }

  const runSummary = (validationMode, fastModeReason, validationRunId) => {
    writeFileSync(githubSummary, "", "utf8");
    const result = runBash(summaryStep.run, {
      EXPECTED_SHA: "a".repeat(40),
      FAST_MODE_REASON: fastModeReason,
      GITHUB_ACTOR: "release-operator",
      GITHUB_STEP_SUMMARY: shellPath(githubSummary),
      VALIDATION_MODE: validationMode,
      VALIDATION_RUN_ID: validationRunId,
    });
    return { result, summary: readFileSync(githubSummary, "utf8") };
  };

  const strictSummary = runSummary("strict", "", "987654321");
  requireCondition(strictSummary.result.status === 0, "Expected strict summary generation to pass.");
  requireCondition(
    strictSummary.summary.includes("Full Validation Artifact: verified") &&
      strictSummary.summary.includes("987654321"),
    "Strict summary must record the verified Full Validation Run.",
  );

  const fastSummary = runSummary("fast", "仅调整低风险展示文案", "");
  requireCondition(fastSummary.result.status === 0, "Expected fast summary generation to pass.");
  requireCondition(
    fastSummary.summary.includes("not required by explicit fast mode") &&
      fastSummary.summary.includes("仅调整低风险展示文案"),
    "Fast summary must record the skipped Artifact and operator reason.",
  );
} finally {
  rmSync(fixtureRoot, { recursive: true, force: true });
}

requireCondition(workflow.jobs?.handoff?.needs === "validate", "CNB handoff must still depend on validation.");
requireCondition(
  workflow.jobs.handoff.steps?.some(
    (step) =>
      step.name === "Push approved commit to CNB" &&
      step.env?.VALIDATION_MODE === "${{ needs.validate.outputs.validation_mode }}" &&
      step.run?.includes("Validation mode: $VALIDATION_MODE"),
  ),
  "The successful CNB handoff summary must retain the validated mode.",
);

console.log(
  "CNB handoff validation-mode fixtures passed: strict default, explicit fast mode, audit summary, and unconditional guards.",
);
