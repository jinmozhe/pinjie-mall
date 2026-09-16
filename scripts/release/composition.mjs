import { createHash } from "node:crypto";

export const apps = ["backend", "admin"];
export const repository = "jinmozhe/pinjie-mall";
export const registry = "ccr.ccs.tencentyun.com/pinjie-mall";
export const shaPattern = /^[0-9a-f]{40}$/u;
export const idPattern = /^[1-9][0-9]*$/u;

export function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

export function exactKeys(value, keys, label) {
  requireCondition(value && typeof value === "object" && !Array.isArray(value) &&
    JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...keys].sort()), `${label}: unexpected or missing fields.`);
}

export function imageReference(app, value) {
  const prefix = `${registry}/pinjie-mall-${app}@sha256:`;
  requireCondition(apps.includes(app) && typeof value === "string" &&
    value.startsWith(prefix) && /^[0-9a-f]{64}$/u.test(value.slice(prefix.length)) &&
    !value.endsWith("0".repeat(64)), `${app}: invalid immutable TCR reference.`);
  return value;
}

export function validateRequest(request) {
  exactKeys(request, ["schema", "test_commit", "images"], "Candidate request");
  requireCondition(request.schema === "pinjie-mall-candidate-request-v1" && shaPattern.test(request.test_commit), "Invalid candidate schema or test commit.");
  exactKeys(request.images, apps, "Candidate images");
  for (const app of apps) {
    const image = request.images[app];
    exactKeys(image, ["release", "handoff_run_id"], `${app} input`);
    const release = image.release;
    requireCondition(idPattern.test(image.handoff_run_id) && release?.schema === "pinjie-cnb-tcr-image-v1" &&
      release.image_key === app && shaPattern.test(release.source?.commit_sha) &&
      release.image?.immutable_tag === `sha-${release.source.commit_sha}`, `${app}: invalid source evidence.`);
    imageReference(app, release.image.reference);
    requireCondition(release.image.reference.endsWith(`@${release.image.digest}`), `${app}: digest mismatch.`);
  }
  return request;
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  return value;
}

export function hash(value) {
  return createHash("sha256").update(JSON.stringify(canonical(value))).digest("hex");
}

export function validateHandoff(evidence, commit, run, attempt) {
  exactKeys(evidence, ["schema", "commit_sha", "mode", "reason", "full_validation_run_id", "run_id", "run_attempt"], "Handoff");
  requireCondition(evidence.schema === "pinjie-source-handoff-v1" && evidence.commit_sha === commit &&
    evidence.run_id === String(run) && evidence.run_attempt === String(attempt), "Handoff identity mismatch.");
  requireCondition(["strict", "fast"].includes(evidence.mode) && typeof evidence.reason === "string", "Invalid handoff mode.");
  if (evidence.mode === "strict") requireCondition(idPattern.test(evidence.full_validation_run_id), "Strict handoff lacks validation Run.");
  else requireCondition(evidence.full_validation_run_id === "" && evidence.reason.trim().length > 0 &&
    evidence.reason.length <= 200 && !/[\r\n]/u.test(evidence.reason), "Fast handoff lacks a valid reason.");
}

export function validateComposition(manifest) {
  exactKeys(manifest, ["schema", "request", "request_sha256", "validation", "handoffs"], "Deployment composition");
  requireCondition(manifest.schema === "pinjie-mall-deployment-composition-v1", "Invalid deployment schema.");
  validateRequest(manifest.request);
  requireCondition(manifest.request_sha256 === hash(manifest.request), "Composition checksum mismatch.");
  exactKeys(manifest.validation, ["status", "run_id", "run_attempt", "workflow_commit", "tested_at", "scope"], "Image validation");
  const validation = manifest.validation;
  requireCondition(validation.status === "passed" && idPattern.test(validation.run_id) && idPattern.test(validation.run_attempt) &&
    shaPattern.test(validation.workflow_commit) && Number.isFinite(Date.parse(validation.tested_at)) &&
    validation.scope === "linux-amd64-postgres-redis-production-images-playwright", "Image validation evidence is incomplete.");
  exactKeys(manifest.handoffs, apps, "Handoffs");
  for (const app of apps) {
    const image = manifest.request.images[app];
    validateHandoff(manifest.handoffs[app], image.release.source.commit_sha, image.handoff_run_id, manifest.handoffs[app].run_attempt);
  }
  return manifest;
}

export function imageVariables(request) {
  validateRequest(request);
  return Object.fromEntries(apps.map((app) => [`${app.toUpperCase()}_IMAGE`, request.images[app].release.image.reference]));
}
