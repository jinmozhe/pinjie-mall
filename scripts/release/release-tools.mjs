import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { parseEnv } from "node:util";
import { fileURLToPath } from "node:url";
import { apps, exactKeys, hash, imageReference, imageVariables, requireCondition, validateComposition, validateRequest } from "./composition.mjs";
import { downloadEvidence, githubRun, run } from "./github-evidence.mjs";

const json = (path) => JSON.parse(readFileSync(path, "utf8"));
const save = (path, value) => writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, { flag: "wx" });

export function deploymentVariables(text) {
  const values = parseEnv(text);
  exactKeys(values, ["BACKEND_IMAGE", "ADMIN_IMAGE"], "Deployment variables");
  const seen = new Set();
  for (const line of text.split(/\r?\n/u)) {
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    const entry = parseEnv(line);
    requireCondition(Object.keys(entry).length === 1, "Deployment variables must use one assignment per line.");
    const key = Object.keys(entry)[0];
    requireCondition(!seen.has(key), "Duplicate deployment variable.");
    seen.add(key);
  }
  for (const app of apps) imageReference(app, values[`${app.toUpperCase()}_IMAGE`]);
  return values;
}

export function retentionPlan(inventory, protectedManifests, now = Date.now()) {
  exactKeys(inventory, ["schema", "captured_at", "tags"], "Registry inventory");
  requireCondition(inventory.schema === "pinjie-tcr-inventory-v1" && Array.isArray(inventory.tags) &&
    protectedManifests.length >= 2, "Supply an inventory plus current production and rollback compositions.");
  const captured = Date.parse(inventory.captured_at);
  requireCondition(Number.isFinite(captured) && captured <= now && now - captured < 24 * 3600_000, "Inventory must be captured within the last 24 hours.");
  const protectedRefs = new Set(protectedManifests.flatMap((manifest) => {
    validateComposition(manifest);
    return apps.map((app) => manifest.request.images[app].release.image.reference);
  }));
  const seen = new Set();
  const observed = new Set();
  const keep = [];
  const review = [];
  for (const item of inventory.tags) {
    exactKeys(item, ["app", "tag", "digest", "created_at"], "Registry tag");
    const reference = imageReference(item.app, `ccr.ccs.tencentyun.com/pinjie-mall/pinjie-mall-${item.app}@${item.digest}`);
    requireCondition(typeof item.tag === "string" && /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$/u.test(item.tag), "Invalid registry tag.");
    requireCondition(!seen.has(`${item.app}:${item.tag}`), "Duplicate registry inventory entry.");
    seen.add(`${item.app}:${item.tag}`);
    observed.add(reference);
    const created = Date.parse(item.created_at);
    requireCondition(Number.isFinite(created) && created <= captured, "Invalid registry tag time.");
    const ageDays = (now - created) / 86400_000;
    let reason = "unrecognized-or-supporting-artifact";
    if (protectedRefs.has(reference)) reason = "production-or-rollback";
    else if (item.tag.startsWith("buildcache")) reason = "build-cache";
    else if (/^candidate-[A-Za-z0-9_.-]+$/u.test(item.tag)) reason = ageDays >= 30 ? "expired-candidate" : "live-candidate";
    else if (/^sha-[0-9a-f]{40}$/u.test(item.tag)) reason = ageDays >= 90 ? "old-source-tag" : "recent-source-tag";
    const entry = { ...item, reason };
    if (["expired-candidate", "old-source-tag"].includes(reason)) review.push(entry);
    else keep.push(entry);
  }
  requireCondition([...protectedRefs].every((ref) => observed.has(ref)), "Inventory is missing protected production or rollback images.");
  return { schema: "pinjie-tcr-retention-plan-v1", mode: "review-only", generated_at: new Date(now).toISOString(),
    protected_compositions: protectedManifests.map(hash), keep, review,
    restrictions: ["No deletion is performed", "Recheck live registry state before any approved tag deletion",
      "Preserve OCI index children, attestations, SBOM, CNB evidence and deployment evidence", "No manifest or blob garbage collection is authorized"] };
}

function argumentsMap(tokens) {
  const result = new Map();
  for (let index = 0; index < tokens.length; index += 2) {
    const key = tokens[index];
    const value = tokens[index + 1];
    requireCondition(key?.startsWith("--") && value && !value.startsWith("--"), "Expected --option value pairs.");
    requireCondition(key === "--protect" || !result.has(key), "Duplicate option.");
    if (key === "--protect") result.set(key, [...(result.get(key) ?? []), value]);
    else result.set(key, value);
  }
  return result;
}

function validateReleaseFiles(request, directory) {
  for (const app of apps) {
    const release = request.images[app].release;
    const path = resolve(directory, `${app}.json`);
    writeFileSync(path, `${JSON.stringify(release)}\n`);
    run(process.execPath, ["scripts/ci/check-cnb-release-evidence.mjs", "--manifest", path, "--expected-image", app,
      "--expected-commit", release.source.commit_sha, "--expected-build-id", release.cnb.build_id]);
  }
}

async function main() {
  const [command, ...tokens] = process.argv.slice(2);
  const args = argumentsMap(tokens);
  const temporary = mkdtempSync(resolve(tmpdir(), "pinjie-release-tools-"));
  try {
    if (command === "request") {
      exactKeys(Object.fromEntries(args), ["--backend", "--admin", "--backend-handoff", "--admin-handoff",
        "--test-commit", "--output"], "Request arguments");
      const request = validateRequest({ schema: "pinjie-mall-candidate-request-v1", test_commit: args.get("--test-commit"),
        images: Object.fromEntries(apps.map((app) => [app, {
          release: json(args.get(`--${app}`)), handoff_run_id: args.get(`--${app}-handoff`),
        }])) });
      validateReleaseFiles(request, temporary);
      save(args.get("--output"), request);
      console.log("Candidate request generated. No workflow or registry operation was triggered.");
    } else if (command === "preflight") {
      exactKeys(Object.fromEntries(args), ["--manifest", "--env-file", "--panel-env"], "Preflight arguments");
      const manifest = validateComposition(json(args.get("--manifest")));
      validateReleaseFiles(manifest.request, temporary);
      const data = githubRun(manifest.validation.run_id, "validate-candidate-images.yml", "main");
      requireCondition(String(data.run_attempt) === manifest.validation.run_attempt && data.head_sha === manifest.validation.workflow_commit,
        "Candidate Run attempt or workflow SHA differs.");
      const trusted = downloadEvidence(manifest.validation.run_id,
        `deployment-composition-${manifest.validation.run_id}-${manifest.validation.run_attempt}`, resolve(temporary, "trusted"), "deployment-composition.json");
      requireCondition(hash(trusted) === hash(manifest), "Local deployment composition differs from the trusted workflow artifact.");
      const expected = imageVariables(manifest.request);
      for (const option of ["--env-file", "--panel-env"]) {
        const values = deploymentVariables(readFileSync(args.get(option), "utf8"));
        for (const key of Object.keys(expected)) requireCondition(values[key] === expected[key], `${option}: ${key} differs from the validated composition.`);
      }
      console.log(`Deployment variable preflight passed; composition=${manifest.request_sha256}. No deployment was performed.`);
    } else if (command === "retention") {
      exactKeys(Object.fromEntries(args), ["--inventory", "--protect", "--output"], "Retention arguments");
      const protectedManifests = args.get("--protect").map(json);
      save(args.get("--output"), retentionPlan(json(args.get("--inventory")), protectedManifests));
      console.log("Registry retention review generated. No registry data was modified.");
    } else throw new Error("Use request, preflight, or retention. See the release runbook for required arguments.");
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();
