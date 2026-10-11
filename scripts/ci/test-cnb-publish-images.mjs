import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const publishScript = path.join(scriptDirectory, "cnb-publish-images.sh");
const fixtureRoot = mkdtempSync(path.join(tmpdir(), "pinjie-cnb-publish-"));
const mockBin = path.join(fixtureRoot, "bin");
const commit = "a".repeat(40);
const commitEpoch = "1788138000";
const digest = `sha256:${"b".repeat(64)}`;

function resolveBashExecutable() {
  if (process.platform !== "win32") {
    return "bash";
  }
  const whereResult = spawnSync("where.exe", ["git.exe"], { encoding: "utf8" });
  const gitExecutable = whereResult.stdout?.split(/\r?\n/u).find(Boolean);
  if (!gitExecutable) {
    throw new Error("Git for Windows is required to run the CNB publish fixtures.");
  }
  return path.join(path.dirname(path.dirname(gitExecutable)), "bin", "bash.exe");
}

function shellPath(value) {
  const normalized = value.replaceAll("\\", "/");
  if (process.platform !== "win32") {
    return normalized;
  }
  return normalized.replace(/^([A-Za-z]):/, (_, drive) => `/${drive.toLowerCase()}`);
}

const bashExecutable = resolveBashExecutable();
const configPreflight = spawnSync(bashExecutable, ["-lc",
  "test ! -e /tmp/pinjie-cnb-docker-config-backend && test ! -e /tmp/pinjie-cnb-docker-config-admin",
], { encoding: "utf8", windowsHide: true });

function runPublish({
  imageKey,
  action = "validate",
  evidenceRoot = `.cnb/evidence/${imageKey}`,
  epoch = commitEpoch,
  targetDigest = "",
  buildScenario = "",
  inspectionScenario = "",
}) {
  const environment = [
    `PATH="${shellPath(mockBin)}:$PATH"`,
    "CNB_BRANCH=main",
    "CNB_BUILD_ID=12345",
    "CNB_BUILD_START_TIME=2026-08-31T01:01:00Z",
    "CNB_BUILD_WEB_URL=https://cnb.cool/pjwl/pinjie-mall/-/build/12345",
    `CNB_COMMIT=${commit}`,
    "CNB_REPO_SLUG=pjwl/pinjie-mall",
    `DOCKER_CONFIG=/tmp/pinjie-cnb-docker-config-${imageKey}`,
    `EVIDENCE_ROOT=${evidenceRoot}`,
    "EXPECTED_CNB_BRANCH=main",
    "EXPECTED_CNB_REPOSITORY=pjwl/pinjie-mall",
    `IMAGE_KEY=${imageKey}`,
    `RELEASE_PIPELINE=${imageKey}-image`,
    `MOCK_COMMIT_EPOCH=${epoch}`,
    `MOCK_BUILD_SCENARIO=${buildScenario}`,
    `MOCK_INSPECTION_SCENARIO=${inspectionScenario}`,
    `MOCK_TARGET_DIGEST=${targetDigest}`,
    `MOCK_STATE_FILE="${shellPath(path.join(fixtureRoot, "created-tag"))}"`,
    `MOCK_EXPECTED_DIGEST=${digest}`,
    "TCR_NAMESPACE=pinjie-mall",
    "TCR_PUBLISH_PASSWORD=test-password",
    "TCR_PUBLISH_USERNAME=test-user",
    "TCR_REGISTRY=ccr.ccs.tencentyun.com",
  ].join(" ");
  return spawnSync(
    bashExecutable,
    ["-lc", `${environment} bash "${shellPath(publishScript)}" ${action}`],
    { cwd: fixtureRoot, encoding: "utf8", windowsHide: true, timeout: 20_000 },
  );
}

function requireCondition(condition, message, result) {
  if (condition) {
    return;
  }
  const detail = result ? `\nstdout:\n${result.stdout ?? ""}\nstderr:\n${result.stderr ?? ""}` : "";
  throw new Error(`${message}${detail}`);
}

try {
  requireCondition(configPreflight.status === 0,
    "Refusing fixtures while fixed Docker configuration paths already exist.", configPreflight);
  mkdirSync(mockBin, { recursive: true });
  writeFileSync(
    path.join(mockBin, "git"),
    `#!/bin/sh
set -eu
if [ "$1" = "rev-parse" ]; then
  printf '%s\\n' '${commit}'
elif [ "$1" = "show" ]; then
  printf '%s\\n' "$MOCK_COMMIT_EPOCH"
else
  exit 2
fi
`,
    "utf8",
  );
  writeFileSync(
    path.join(mockBin, "docker"),
    `#!/bin/sh
set -eu
if [ "$1" = "login" ]; then
  cat >/dev/null
elif [ "$1" = "buildx" ] && [ "$2" = "version" ]; then
  printf 'buildx fixture\\n'
elif [ "$1" = "buildx" ] && [ "$2" = "build" ]; then
  printf '%s\\n' "$@" > build-args.txt
  case " $* " in *--cache-from*|*--cache-to*) exit 90 ;; esac
  if [ "$MOCK_BUILD_SCENARIO" = "build-failure" ]; then exit 42; fi
  : > build-finished
elif [ "$1" = "buildx" ] && [ "$2" = "imagetools" ] && [ "$3" = "inspect" ]; then
  case "$MOCK_INSPECTION_SCENARIO" in
    unauthorized) echo 'ERROR: unexpected status: 401 Unauthorized' >&2; exit 1 ;;
    forbidden) echo 'ERROR: unexpected status: 403 Forbidden' >&2; exit 1 ;;
    timeout) echo 'ERROR: context deadline exceeded' >&2; exit 1 ;;
    server-error) echo 'ERROR: unexpected status: 503 Service Unavailable' >&2; exit 1 ;;
    unknown) echo 'ERROR: registry response is unknown' >&2; exit 1 ;;
    wrong-reference) echo 'ERROR: another/image:tag: not found' >&2; exit 1 ;;
    credential-helper) echo 'ERROR: credential helper not found' >&2; exit 1 ;;
    mixed-error) printf 'ERROR: %s: not found\\nERROR: context deadline exceeded\\n' "$4" >&2; exit 1 ;;
    digest-then-error) printf 'Digest: %s\\n' "$MOCK_EXPECTED_DIGEST"; echo 'ERROR: read failed' >&2; exit 1 ;;
    empty-error) exit 1 ;;
    empty-success) exit 0 ;;
    malformed-digest) echo 'Digest: sha256:wrong'; exit 0 ;;
    existing) printf 'Digest: %s\\n' "$MOCK_EXPECTED_DIGEST"; exit 0 ;;
  esac
  if [ -n "$MOCK_BUILD_SCENARIO" ]; then
    if [ ! -f build-finished ]; then
      printf 'ERROR: %s: not found\\n' "$4" >&2
      exit 1
    fi
    [ "$MOCK_BUILD_SCENARIO" != "registry-failure" ] || exit 1
    if [ "$MOCK_BUILD_SCENARIO" = "digest-mismatch" ]; then
      printf 'Digest: sha256:wrong\\n'
    else
      printf 'Digest: %s\\n' "$MOCK_EXPECTED_DIGEST"
    fi
    exit 0
  fi
  if [ "$MOCK_TARGET_DIGEST" = "missing" ] && [ ! -f "$MOCK_STATE_FILE" ]; then
    printf 'ERROR: %s: not found\\n' "$4" >&2
    exit 1
  fi
  if [ "$MOCK_TARGET_DIGEST" = "missing" ]; then
    printf 'Digest: %s\\n' "$MOCK_EXPECTED_DIGEST"
  else
    printf 'Digest: %s\\n' "$MOCK_TARGET_DIGEST"
  fi
elif [ "$1" = "buildx" ] && [ "$2" = "imagetools" ] && [ "$3" = "create" ]; then
  : > "$MOCK_STATE_FILE"
else
  exit 2
fi
`,
    "utf8",
  );
  writeFileSync(path.join(mockBin, "jq"), `#!/bin/sh
set -eu
if [ "$1" = "-er" ]; then
  [ "$MOCK_BUILD_SCENARIO" != "missing-metadata" ] || exit 1
  printf '%s\\n' "$MOCK_EXPECTED_DIGEST"
fi
case "$*" in
  *attestation-manifest*) [ "$MOCK_BUILD_SCENARIO" != "attestation-failure" ] || exit 1 ;;
  *org.opencontainers.image.revision*) [ "$MOCK_BUILD_SCENARIO" != "labels-failure" ] || exit 1 ;;
esac
`, "utf8");
  for (const command of ["git", "docker", "jq"]) {
    chmodSync(path.join(mockBin, command), 0o755);
  }

  for (const imageKey of ["backend", "admin"]) {
    const result = runPublish({ imageKey });
    requireCondition(result.status === 0, `Expected ${imageKey} release context to pass.`, result);
    const evidenceRoot = path.join(fixtureRoot, ".cnb", "evidence", imageKey);
    requireCondition(existsSync(path.join(evidenceRoot, "source-commit-epoch.txt")), "Commit epoch evidence is missing.", result);
    requireCondition(readFileSync(path.join(evidenceRoot, "source-commit-epoch.txt"), "utf8").trim() === commitEpoch, "Commit epoch is incorrect.", result);
    requireCondition(readFileSync(path.join(evidenceRoot, "source-commit-time.txt"), "utf8").trim() === "2026-08-31T01:00:00Z", "Commit UTC time is incorrect.", result);
  }

  mkdirSync(path.join(fixtureRoot, "apps", "backend"), { recursive: true });
  writeFileSync(path.join(fixtureRoot, "apps", "backend", "Dockerfile"), "FROM fixture\n");
  for (const [scenario, reason] of [
    ["success", ""], ["build-failure", ""],
    ["missing-metadata", "does not contain containerimage.digest"],
    ["registry-failure", "Candidate registry inspection failed"],
    ["digest-mismatch", "Candidate digest mismatch"],
    ["attestation-failure", "missing an attestation"],
    ["labels-failure", "labels do not match"],
  ]) {
    const evidence = path.join(fixtureRoot, ".cnb", "evidence", "backend", "backend-digest.txt");
    rmSync(path.join(fixtureRoot, "build-finished"), { force: true });
    rmSync(evidence, { force: true });
    const result = runPublish({ imageKey: "backend", action: "build", buildScenario: scenario });
    requireCondition(scenario === "success" ? result.status === 0 : result.status !== 0, scenario, result);
    requireCondition(scenario === "success" ? existsSync(evidence) : !existsSync(evidence), "Digest evidence must follow successful validation", result);
    if (reason) requireCondition(result.stdout.includes(reason), "Missing actionable failure reason", result);
    const args = readFileSync(path.join(fixtureRoot, "build-args.txt"), "utf8");
    requireCondition(!args.includes("--cache-from") && !args.includes("--cache-to"), "Registry cache must remain disabled");
    requireCondition(args.includes("--provenance=mode=max") && args.includes("--sbom=true") && args.includes("push=true"), "Required publish outputs are missing");
  }

  const unknownResult = runPublish({ imageKey: "worker" });
  requireCondition(unknownResult.status !== 0, "Expected an unknown IMAGE_KEY to fail.", unknownResult);
  const escapedResult = runPublish({ imageKey: "backend", evidenceRoot: ".cnb/evidence/web" });
  requireCondition(escapedResult.status !== 0, "Expected an incorrect evidence path to fail.", escapedResult);
  const invalidEpochResult = runPublish({ imageKey: "backend", epoch: "0" });
  requireCondition(invalidEpochResult.status !== 0, "Expected an invalid Git commit epoch to fail.", invalidEpochResult);

  const digestFile = path.join(fixtureRoot, ".cnb", "evidence", "backend", "backend-digest.txt");
  writeFileSync(digestFile, `${digest}\n`, "utf8");
  for (const inspectionScenario of [
    "unauthorized", "forbidden", "timeout", "server-error", "unknown", "wrong-reference",
    "credential-helper", "mixed-error", "digest-then-error", "empty-error", "empty-success", "malformed-digest",
  ]) {
    for (const action of ["build", "finalize"]) {
      rmSync(path.join(fixtureRoot, "created-tag"), { force: true });
      rmSync(path.join(fixtureRoot, "build-args.txt"), { force: true });
      const result = runPublish({ imageKey: "backend", action, inspectionScenario });
      requireCondition(result.status !== 0, `${action} must reject ${inspectionScenario}.`, result);
      requireCondition(!existsSync(path.join(fixtureRoot, "created-tag")), "Unknown tag state must not create a tag.", result);
      requireCondition(!existsSync(path.join(fixtureRoot, "build-args.txt")), "Unknown tag state must not build or push.", result);
      requireCondition(result.stdout.includes("absence could not be confirmed"), "Expected explicit failure before write.", result);
      requireCondition(result.stderr.includes("Registry inspection"), "Expected retained inspection failure diagnostics.", result);
    }
  }
  const existingCandidate = runPublish({ imageKey: "backend", action: "build", inspectionScenario: "existing" });
  requireCondition(existingCandidate.status !== 0, "Existing candidate tag must block building.", existingCandidate);
  requireCondition(!existsSync(path.join(fixtureRoot, "build-args.txt")), "Existing candidate must not be overwritten.");
  const conflictResult = runPublish({
    imageKey: "backend",
    action: "finalize",
    targetDigest: `sha256:${"c".repeat(64)}`,
  });
  requireCondition(conflictResult.status !== 0, "Expected an immutable SHA tag conflict to fail.", conflictResult);
  requireCondition(!existsSync(path.join(fixtureRoot, "created-tag")), "Conflicting SHA tag must remain unchanged.");

  const idempotentResult = runPublish({ imageKey: "backend", action: "finalize", targetDigest: digest });
  requireCondition(idempotentResult.status === 0, "Expected the same SHA tag digest to pass.", idempotentResult);
  requireCondition(!existsSync(path.join(fixtureRoot, "created-tag")), "Matching SHA digest must not rewrite the tag.");

  rmSync(path.join(fixtureRoot, "created-tag"), { force: true });
  const createResult = runPublish({ imageKey: "backend", action: "finalize", targetDigest: "missing" });
  requireCondition(createResult.status === 0, "Expected a missing SHA tag to be created.", createResult);
  requireCondition(existsSync(path.join(fixtureRoot, "created-tag")), "Expected the mock SHA tag creation.", createResult);

  for (const imageKey of ["backend", "admin"]) {
    const cleanupResult = runPublish({ imageKey, action: "cleanup" });
    requireCondition(cleanupResult.status === 0, `Expected ${imageKey} Docker configuration cleanup to pass.`, cleanupResult);
  }

  console.log("CNB single-image publish context and finalize fixtures passed.");
} finally {
  if (configPreflight.status === 0) {
    for (const imageKey of ["backend", "admin"]) {
      runPublish({ imageKey, action: "cleanup" });
    }
  }
  requireCondition(path.dirname(fixtureRoot) === path.resolve(tmpdir()) && path.basename(fixtureRoot).startsWith("pinjie-cnb-publish-"),
    "Refusing cleanup outside the owned fixture directory.");
  rmSync(fixtureRoot, { recursive: true, force: true });
}
