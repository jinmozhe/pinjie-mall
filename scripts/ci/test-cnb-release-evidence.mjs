import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const guardScript = path.join(scriptDirectory, "check-cnb-release-evidence.mjs");
const createScript = path.join(scriptDirectory, "create-cnb-release-evidence.mjs");
const fixtureRoot = await mkdtemp(path.join(tmpdir(), "pinjie-cnb-release-evidence-"));
const relativeEvidenceRoot = ".cnb/evidence/backend";
const evidenceRoot = path.join(fixtureRoot, relativeEvidenceRoot);
const manifestPath = path.join(evidenceRoot, "backend-release-manifest.json");
const expectedCommit = "a".repeat(40);
const expectedBuildId = "987654321";
const digest = `sha256:${"b".repeat(64)}`;
const commitEpoch = 1788138000;
const commitTime = "2026-08-31T01:00:00Z";

await mkdir(evidenceRoot, { recursive: true });
await Promise.all([
  writeFile(path.join(evidenceRoot, "source-commit-epoch.txt"), `${commitEpoch}\n`, "utf8"),
  writeFile(path.join(evidenceRoot, "source-commit-time.txt"), `${commitTime}\n`, "utf8"),
  writeFile(path.join(evidenceRoot, "backend-digest.txt"), `${digest}\n`, "utf8"),
  writeFile(path.join(evidenceRoot, "backend-trivy.json"), '{"Results":[]}\n', "utf8"),
  writeFile(
    path.join(evidenceRoot, "backend-sbom.cdx.json"),
    '{"bomFormat":"CycloneDX","specVersion":"1.6"}\n',
    "utf8",
  ),
  writeFile(
    path.join(evidenceRoot, "backend-metadata.json"),
    `${JSON.stringify({
      "containerimage.digest": digest,
      "buildx.build.provenance": { buildType: "https://mobyproject.org/buildkit@v1" },
    })}\n`,
    "utf8",
  ),
  writeFile(
    path.join(evidenceRoot, "backend-image.json"),
    `${JSON.stringify({
      created: commitTime,
      config: {
        Labels: {
          "org.opencontainers.image.revision": expectedCommit,
          "org.opencontainers.image.created": commitTime,
          "org.opencontainers.image.source": "https://github.com/jinmozhe/pinjie-mall",
        },
      },
    })}\n`,
    "utf8",
  ),
]);

const createEnvironment = {
  ...process.env,
  EVIDENCE_ROOT: relativeEvidenceRoot,
  IMAGE_KEY: "backend",
  CNB_COMMIT: expectedCommit,
  TCR_REGISTRY: "ccr.ccs.tencentyun.com",
  TCR_NAMESPACE: "pinjie-mall",
  RELEASE_PIPELINE: "backend-image",
  CNB_BUILD_START_TIME: "2026-08-31T01:01:00.000Z",
  CNB_REPO_SLUG: "pjwl/pinjie-mall",
  CNB_BRANCH: "main",
  CNB_BUILD_ID: expectedBuildId,
  CNB_BUILD_WEB_URL: `https://cnb.cool/pjwl/pinjie-mall/-/build/logs/${expectedBuildId}`,
};
const createResult = spawnSync(process.execPath, [createScript], {
  cwd: fixtureRoot,
  env: createEnvironment,
  encoding: "utf8",
});
if (createResult.status !== 0) {
  throw new Error(`Expected release evidence generation to pass: ${createResult.stderr}`);
}
const validManifest = JSON.parse(await readFile(manifestPath, "utf8"));

async function runGuard(manifest, expectedImage = "backend") {
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
  return spawnSync(
    process.execPath,
    [
      guardScript,
      "--manifest",
      manifestPath,
      "--expected-image",
      expectedImage,
      "--expected-commit",
      expectedCommit,
      "--expected-build-id",
      expectedBuildId,
    ],
    { encoding: "utf8" },
  );
}

async function expectRejected(label, mutate, expectedImage = "backend") {
  const fixture = structuredClone(validManifest);
  mutate(fixture);
  const result = await runGuard(fixture, expectedImage);
  if (result.status === 0) {
    throw new Error(`Expected release evidence guard to reject ${label}.`);
  }
}

try {
  const validResult = await runGuard(validManifest);
  if (validResult.status !== 0) {
    throw new Error(`Expected valid release evidence to pass: ${validResult.stderr}`);
  }

  await expectRejected("an unknown image key", () => {}, "worker");
  await expectRejected("wrong commit SHA", (fixture) => {
    fixture.source.commit_sha = "c".repeat(40);
  });
  await expectRejected("wrong build ID", (fixture) => {
    fixture.cnb.build_id = "123";
  });
  await expectRejected("wrong build URL", (fixture) => {
    fixture.cnb.build_url = "https://cnb.cool/pjwl/pinjie-mall/-/build/logs/123";
  });
  await expectRejected("wrong pipeline", (fixture) => {
    fixture.cnb.pipeline = "web-image";
  });
  await expectRejected("unexpected field", (fixture) => {
    fixture.result = "success";
  });
  await expectRejected("digest mismatch", (fixture) => {
    fixture.image.digest = `sha256:${"d".repeat(64)}`;
  });
  await expectRejected("failed scan", (fixture) => {
    fixture.image.trivy = "failed";
  });
  await expectRejected("invalid SBOM status", (fixture) => {
    fixture.image.sbom = "missing";
  });
  await expectRejected("invalid provenance status", (fixture) => {
    fixture.image.provenance = "missing";
  });
  await expectRejected("mismatched commit time", (fixture) => {
    fixture.source.commit_epoch += 1;
  });
  await expectRejected("mismatched OCI revision", (fixture) => {
    fixture.image.oci.revision = "c".repeat(40);
  });
  await expectRejected("mismatched OCI creation time", (fixture) => {
    fixture.image.oci.created = "2026-08-31T01:00:01Z";
  });
  await expectRejected("a non-RFC timestamp", (fixture) => {
    fixture.source.commit_time = "2026-08-31";
  });

  await rm(path.join(evidenceRoot, "backend-sbom.cdx.json"), { force: true });
  const missingSbomResult = spawnSync(process.execPath, [createScript], {
    cwd: fixtureRoot,
    env: createEnvironment,
    encoding: "utf8",
  });
  if (missingSbomResult.status === 0) {
    throw new Error("Expected release evidence generation to reject a missing SBOM.");
  }

  console.log("CNB single-image release evidence guard fixtures passed.");
} finally {
  await rm(fixtureRoot, { recursive: true, force: true });
}
