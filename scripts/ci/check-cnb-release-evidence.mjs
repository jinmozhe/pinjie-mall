import { readFile } from "node:fs/promises";

const expectedImages = {
  backend: "pinjie-mall-backend",
  admin: "pinjie-mall-admin",
};
const expectedRegistry = "ccr.ccs.tencentyun.com";
const expectedNamespace = "pinjie-mall";
const expectedSourceRepository = "https://github.com/jinmozhe/pinjie-mall";

function parseArguments(argv) {
  const allowed = new Set([
    "--manifest",
    "--expected-image",
    "--expected-commit",
    "--expected-build-id",
  ]);
  const result = new Map();
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!allowed.has(key) || !value) {
      throw new Error("Arguments must use the supported --name value pairs.");
    }
    if (result.has(key)) {
      throw new Error(`Duplicate argument ${key}.`);
    }
    result.set(key, value);
  }
  return result;
}

function exactKeys(value, expected, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    throw new Error(`${label} fields do not match the schema.`);
  }
}

function requireEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label} does not match.`);
  }
}

function requireTimestamp(value, label) {
  const rfc3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u;
  if (typeof value !== "string" || !rfc3339.test(value) || Number.isNaN(Date.parse(value))) {
    throw new Error(`${label} must be an RFC 3339 timestamp.`);
  }
}

const args = parseArguments(process.argv.slice(2));
const manifestPath = args.get("--manifest");
const expectedImage = args.get("--expected-image");
const expectedCommit = args.get("--expected-commit");
const expectedBuildId = args.get("--expected-build-id");
const expectedRepository = expectedImages[expectedImage];

if (
  !manifestPath ||
  !expectedRepository ||
  !expectedBuildId ||
  !/^[0-9a-f]{40}$/.test(expectedCommit ?? "")
) {
  throw new Error("Manifest path, known image, full commit SHA, and build ID are required.");
}

const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
exactKeys(
  manifest,
  ["schema", "image_key", "source", "cnb", "registry", "namespace", "image"],
  "Image release manifest",
);
requireEqual(manifest.schema, "pinjie-cnb-tcr-image-v1", "Release schema");
requireEqual(manifest.image_key, expectedImage, "Image key");
requireEqual(manifest.registry, expectedRegistry, "Registry");
requireEqual(manifest.namespace, expectedNamespace, "Namespace");

exactKeys(manifest.source, ["commit_sha", "commit_epoch", "commit_time"], "Source evidence");
requireEqual(manifest.source.commit_sha, expectedCommit, "Commit SHA");
if (!Number.isSafeInteger(manifest.source.commit_epoch) || manifest.source.commit_epoch <= 0) {
  throw new Error("Commit epoch must be a positive safe integer.");
}
requireTimestamp(manifest.source.commit_time, "Commit time");
if (Math.floor(Date.parse(manifest.source.commit_time) / 1000) !== manifest.source.commit_epoch) {
  throw new Error("Commit epoch and time do not identify the same instant.");
}

exactKeys(
  manifest.cnb,
  ["repository", "branch", "pipeline", "build_id", "build_url", "started_at", "finished_at"],
  "CNB evidence",
);
requireEqual(manifest.cnb.repository, "pjwl/pinjie-mall", "CNB repository");
requireEqual(manifest.cnb.branch, "main", "CNB branch");
requireEqual(manifest.cnb.pipeline, `${expectedImage}-image`, "CNB pipeline");
requireEqual(manifest.cnb.build_id, expectedBuildId, "CNB build ID");
requireTimestamp(manifest.cnb.started_at, "CNB start time");
requireTimestamp(manifest.cnb.finished_at, "CNB finish time");
if (Date.parse(manifest.cnb.finished_at) < Date.parse(manifest.cnb.started_at)) {
  throw new Error("CNB finish time cannot precede start time.");
}

const buildUrl = new URL(manifest.cnb.build_url);
requireEqual(buildUrl.origin, "https://cnb.cool", "CNB build URL origin");
if (!buildUrl.pathname.startsWith("/pjwl/pinjie-mall/-/build/")) {
  throw new Error("CNB build URL path does not match the repository.");
}
if (!buildUrl.pathname.endsWith(`/${expectedBuildId}`)) {
  throw new Error("CNB build URL does not match the Build ID.");
}

exactKeys(
  manifest.image,
  ["repository", "digest", "reference", "immutable_tag", "trivy", "sbom", "provenance", "oci"],
  "Image evidence",
);
requireEqual(manifest.image.repository, expectedRepository, "Image repository");
if (!/^sha256:[0-9a-f]{64}$/.test(manifest.image.digest)) {
  throw new Error("Image digest is invalid.");
}
requireEqual(
  manifest.image.reference,
  `${expectedRegistry}/${expectedNamespace}/${expectedRepository}@${manifest.image.digest}`,
  "Immutable image reference",
);
requireEqual(manifest.image.immutable_tag, `sha-${expectedCommit}`, "Immutable image tag");
requireEqual(manifest.image.trivy, "passed", "Trivy status");
requireEqual(manifest.image.sbom, "cyclonedx-json", "SBOM status");
requireEqual(manifest.image.provenance, "buildkit-max", "Provenance status");

exactKeys(manifest.image.oci, ["revision", "created", "source"], "OCI evidence");
requireEqual(manifest.image.oci.revision, expectedCommit, "OCI revision");
requireEqual(manifest.image.oci.created, manifest.source.commit_time, "OCI creation time");
requireEqual(manifest.image.oci.source, expectedSourceRepository, "OCI source");

console.log(
  `CNB ${expectedImage} image evidence matches commit ${expectedCommit} and build ${expectedBuildId}.`,
);
