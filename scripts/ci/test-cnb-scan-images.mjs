import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const scanScript = path.join(scriptDirectory, "cnb-scan-images.sh");
const fixtureRoot = mkdtempSync(path.join(process.cwd(), ".tmp-cnb-scan-"));
const mockBin = path.join(fixtureRoot, "bin");
const digest = `sha256:${"a".repeat(64)}`;

function resolveBashExecutable() {
  if (process.platform !== "win32") {
    return "bash";
  }
  const whereResult = spawnSync("where.exe", ["git.exe"], { encoding: "utf8" });
  const gitExecutable = whereResult.stdout?.split(/\r?\n/u).find(Boolean);
  if (!gitExecutable) {
    throw new Error("Git for Windows is required to run the CNB scan fixtures.");
  }
  const candidate = path.join(path.dirname(path.dirname(gitExecutable)), "bin", "bash.exe");
  if (!existsSync(candidate)) {
    throw new Error(`Git Bash was not found at ${candidate}.`);
  }
  return candidate;
}

const bashExecutable = resolveBashExecutable();

function shellPath(value) {
  const normalized = value.replaceAll("\\", "/");
  if (process.platform !== "win32") {
    return normalized;
  }
  return normalized.replace(/^([A-Za-z]):/, (_, drive) => `/${drive.toLowerCase()}`);
}

function runScan(imageKey, blocked = false) {
  const evidenceRoot = path.join(fixtureRoot, ".cnb", "evidence", imageKey);
  rmSync(evidenceRoot, { recursive: true, force: true });
  mkdirSync(evidenceRoot, { recursive: true });
  writeFileSync(path.join(fixtureRoot, "trivy-calls.txt"), "", "utf8");
  writeFileSync(path.join(evidenceRoot, `${imageKey}-digest.txt`), `${digest}\n`, "utf8");
  const environment = [
    `PATH="${shellPath(mockBin)}:$PATH"`,
    `EVIDENCE_ROOT=".cnb/evidence/${imageKey}"`,
    `IMAGE_KEY=${imageKey}`,
    "TCR_REGISTRY=ccr.ccs.tencentyun.com",
    "TCR_NAMESPACE=pinjie-mall",
    "TCR_PUBLISH_USERNAME=test-user",
    "TCR_PUBLISH_PASSWORD=test-password",
    `MOCK_BLOCK=${blocked ? "1" : "0"}`,
  ].join(" ");
  const result = spawnSync(bashExecutable, ["-lc", `${environment} sh "${shellPath(scanScript)}"`], {
    cwd: fixtureRoot,
    encoding: "utf8",
  });
  return { evidenceRoot, result };
}

function requireCondition(condition, message, result) {
  if (condition) {
    return;
  }
  const detail = result
    ? `\nerror:\n${result.error ?? "none"}\nstdout:\n${result.stdout ?? ""}\nstderr:\n${result.stderr ?? ""}`
    : "";
  throw new Error(`${message}${detail}`);
}

try {
  mkdirSync(mockBin, { recursive: true });
  const mockTrivy = path.join(mockBin, "trivy");
  writeFileSync(
    mockTrivy,
    `#!/bin/sh
set -eu
printf '%s\\n' "$1" >> trivy-calls.txt
format=""
output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --format)
      shift
      format="$1"
      ;;
    --output)
      shift
      output="$1"
      ;;
  esac
  shift
done
mkdir -p "$(dirname "$output")"
case "$format" in
  json)
    printf '{"Results":[]}\n' > "$output"
    ;;
  table)
    if [ "\${MOCK_BLOCK:-0}" = "1" ]; then
      printf 'Library  Vulnerability  Severity  Installed  Fixed\\nlibfixture  CVE-2099-0001  HIGH  1.0-r0  1.0-r1\\n' > "$output"
      exit 1
    fi
    printf 'Total: 0 (HIGH: 0, CRITICAL: 0)\\n' > "$output"
    ;;
  cyclonedx)
    printf '{"bomFormat":"CycloneDX","specVersion":"1.6"}\n' > "$output"
    ;;
  *)
    printf 'Unexpected format: %s\n' "$format" >&2
    exit 2
    ;;
esac
`,
    "utf8",
  );
  chmodSync(mockTrivy, 0o755);

  for (const imageKey of ["backend", "admin"]) {
    const { evidenceRoot, result } = runScan(imageKey);
    requireCondition(result.status === 0, `Expected ${imageKey} scan to pass.`, result);
    requireCondition(existsSync(path.join(evidenceRoot, `${imageKey}-trivy-full.json`)), `Expected ${imageKey} complete JSON evidence.`, result);
    requireCondition(existsSync(path.join(evidenceRoot, `${imageKey}-sbom.cdx.json`)), `Expected ${imageKey} SBOM evidence.`, result);
    requireCondition(readFileSync(path.join(fixtureRoot, "trivy-calls.txt"), "utf8").trim() === "image\nconvert\nconvert", "Expected one image scan and two offline conversions.", result);
  }

  const { evidenceRoot: blockedRoot, result: blockedResult } = runScan("admin", true);
  requireCondition(blockedResult.status === 1, "Expected Admin vulnerability to block only its scan.", blockedResult);
  const summaryPath = path.join(blockedRoot, "scan-failure-summary.txt");
  requireCondition(existsSync(summaryPath), "Expected a failure summary.", blockedResult);
  const summary = readFileSync(summaryPath, "utf8");
  requireCondition(summary.includes("image=admin"), "Expected the summary to identify Admin.", blockedResult);
  requireCondition(summary.includes("CVE-2099-0001"), "Expected the summary to include the CVE.", blockedResult);
  requireCondition(!existsSync(path.join(blockedRoot, "admin-sbom.cdx.json")), "Blocked Admin must not have a success SBOM.", blockedResult);

  const invalidResult = runScan("worker").result;
  requireCondition(invalidResult.status !== 0, "Expected an unknown image key to fail.", invalidResult);

  console.log("CNB single-image scan fixtures passed.");
} finally {
  rmSync(fixtureRoot, { recursive: true, force: true });
}
