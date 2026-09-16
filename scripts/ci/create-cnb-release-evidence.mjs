import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const imageDefinitions = {
  backend: "pinjie-mall-backend",
  admin: "pinjie-mall-admin",
};
const expectedRegistry = "ccr.ccs.tencentyun.com";
const expectedNamespace = "pinjie-mall";
const expectedSourceRepository = "https://github.com/jinmozhe/pinjie-mall";

function requiredEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Required environment variable ${name} is missing.`);
  }
  return value;
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function readText(filePath) {
  return (await readFile(filePath, "utf8")).trim();
}

function hasBlockingVulnerability(report) {
  if (!Array.isArray(report.Results)) {
    throw new Error("Trivy report does not contain a Results array.");
  }
  return report.Results.some((result) =>
    (result.Vulnerabilities ?? []).some((vulnerability) =>
      ["HIGH", "CRITICAL"].includes(vulnerability.Severity),
    ),
  );
}

function requireTimestamp(value, label) {
  const rfc3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u;
  if (typeof value !== "string" || !rfc3339.test(value) || Number.isNaN(Date.parse(value))) {
    throw new Error(`${label} must be an RFC 3339 timestamp.`);
  }
}

const evidenceRoot = requiredEnv("EVIDENCE_ROOT");
const imageKey = requiredEnv("IMAGE_KEY");
const commitSha = requiredEnv("CNB_COMMIT");
const registry = requiredEnv("TCR_REGISTRY");
const namespace = requiredEnv("TCR_NAMESPACE");
const releasePipeline = requiredEnv("RELEASE_PIPELINE");
const repository = imageDefinitions[imageKey];

if (!repository) {
  throw new Error("IMAGE_KEY must be one of backend or admin.");
}
if (evidenceRoot !== `.cnb/evidence/${imageKey}`) {
  throw new Error("EVIDENCE_ROOT does not match IMAGE_KEY.");
}
if (releasePipeline !== `${imageKey}-image`) {
  throw new Error("RELEASE_PIPELINE does not match IMAGE_KEY.");
}
if (!/^[0-9a-f]{40}$/.test(commitSha)) {
  throw new Error("CNB_COMMIT must be a full lowercase 40-character SHA.");
}
if (registry !== expectedRegistry || namespace !== expectedNamespace) {
  throw new Error("TCR registry or namespace does not match the release boundary.");
}

const commitEpochText = await readText(path.join(evidenceRoot, "source-commit-epoch.txt"));
const commitTime = await readText(path.join(evidenceRoot, "source-commit-time.txt"));
if (!/^[1-9][0-9]*$/.test(commitEpochText)) {
  throw new Error("Source commit epoch must be a positive integer.");
}
const commitEpoch = Number(commitEpochText);
requireTimestamp(commitTime, "Source commit time");
if (!Number.isSafeInteger(commitEpoch) || Math.floor(Date.parse(commitTime) / 1000) !== commitEpoch) {
  throw new Error("Source commit epoch and time do not identify the same instant.");
}

const digest = await readText(path.join(evidenceRoot, `${imageKey}-digest.txt`));
if (!/^sha256:[0-9a-f]{64}$/.test(digest)) {
  throw new Error(`Digest evidence for ${imageKey} is invalid.`);
}

const trivy = await readJson(path.join(evidenceRoot, `${imageKey}-trivy.json`));
if (hasBlockingVulnerability(trivy)) {
  throw new Error(`Trivy evidence for ${imageKey} contains a blocking vulnerability.`);
}

const sbom = await readJson(path.join(evidenceRoot, `${imageKey}-sbom.cdx.json`));
if (sbom.bomFormat !== "CycloneDX" || typeof sbom.specVersion !== "string") {
  throw new Error(`SBOM evidence for ${imageKey} is not valid CycloneDX JSON.`);
}

const metadata = await readJson(path.join(evidenceRoot, `${imageKey}-metadata.json`));
if (metadata["containerimage.digest"] !== digest) {
  throw new Error(`Build metadata digest for ${imageKey} does not match.`);
}
if (typeof metadata["buildx.build.provenance"]?.buildType !== "string") {
  throw new Error(`Build provenance metadata for ${imageKey} is missing.`);
}

const imageConfig = await readJson(path.join(evidenceRoot, `${imageKey}-image.json`));
const labels = imageConfig.config?.Labels;
if (
  labels?.["org.opencontainers.image.revision"] !== commitSha ||
  labels?.["org.opencontainers.image.created"] !== commitTime ||
  labels?.["org.opencontainers.image.source"] !== expectedSourceRepository
) {
  throw new Error(`OCI labels for ${imageKey} do not match the release source.`);
}
requireTimestamp(imageConfig.created, "OCI image creation time");
if (Math.floor(Date.parse(imageConfig.created) / 1000) !== commitEpoch) {
  throw new Error(`OCI image creation time for ${imageKey} does not match the Git commit.`);
}

const startedAt = requiredEnv("CNB_BUILD_START_TIME");
const finishedAt = new Date().toISOString();
requireTimestamp(startedAt, "CNB start time");

const manifest = {
  schema: "pinjie-cnb-tcr-image-v1",
  image_key: imageKey,
  source: {
    commit_sha: commitSha,
    commit_epoch: commitEpoch,
    commit_time: commitTime,
  },
  cnb: {
    repository: requiredEnv("CNB_REPO_SLUG"),
    branch: requiredEnv("CNB_BRANCH"),
    pipeline: releasePipeline,
    build_id: requiredEnv("CNB_BUILD_ID"),
    build_url: requiredEnv("CNB_BUILD_WEB_URL"),
    started_at: startedAt,
    finished_at: finishedAt,
  },
  registry,
  namespace,
  image: {
    repository,
    digest,
    reference: `${registry}/${namespace}/${repository}@${digest}`,
    immutable_tag: `sha-${commitSha}`,
    trivy: "passed",
    sbom: "cyclonedx-json",
    provenance: "buildkit-max",
    oci: {
      revision: commitSha,
      created: commitTime,
      source: expectedSourceRepository,
    },
  },
};

await mkdir(evidenceRoot, { recursive: true });
await writeFile(
  path.join(evidenceRoot, `${imageKey}-release-manifest.json`),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);
