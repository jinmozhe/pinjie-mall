import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const publishScript = path.join(scriptDirectory, "cnb-publish-images.sh");
const fixtureRoot = mkdtempSync(path.join(process.cwd(), ".tmp-cnb-publish-"));
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

function runPublish({
  imageKey,
  action = "validate",
  evidenceRoot = `.cnb/evidence/${imageKey}`,
  epoch = commitEpoch,
  targetDigest = "",
  buildScenario = "",
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
    { cwd: fixtureRoot, encoding: "utf8" },
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
  if [ -n "$MOCK_BUILD_SCENARIO" ]; then
    [ -f build-finished ] || exit 1
    [ "$MOCK_BUILD_SCENARIO" != "registry-failure" ] || exit 1
    if [ "$MOCK_BUILD_SCENARIO" = "digest-mismatch" ]; then
      printf 'Digest: sha256:wrong\\n'
    else
      printf 'Digest: %s\\n' "$MOCK_EXPECTED_DIGEST"
    fi
    exit 0
  fi
  if [ "$MOCK_TARGET_DIGEST" = "missing" ] && [ ! -f "$MOCK_STATE_FILE" ]; then
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
  const conflictResult = runPublish({
    imageKey: "backend",
    action: "finalize",
    targetDigest: `sha256:${"c".repeat(64)}`,
  });
  requireCondition(conflictResult.status !== 0, "Expected an immutable SHA tag conflict to fail.", conflictResult);

  const idempotentResult = runPublish({ imageKey: "backend", action: "finalize", targetDigest: digest });
  requireCondition(idempotentResult.status === 0, "Expected the same SHA tag digest to pass.", idempotentResult);

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
  for (const imageKey of ["backend", "admin"]) {
    runPublish({ imageKey, action: "cleanup" });
  }
  rmSync(fixtureRoot, { recursive: true, force: true });
}
