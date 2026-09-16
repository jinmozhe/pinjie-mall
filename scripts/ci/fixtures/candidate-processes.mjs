import assert from "node:assert/strict";
import childProcess from "node:child_process";
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { resolve } from "node:path";

const original = childProcess.spawnSync;
const request = JSON.parse(process.env.CANDIDATE_REQUEST_JSON);
const mode = process.env.PINJIE_CANDIDATE_FIXTURE;
const trace = resolve(process.env.RUNNER_TEMP, "commands.jsonl");
const ok = (value = "") => ({ status: 0, stdout: typeof value === "string" ? value : JSON.stringify(value), stderr: "" });
const fail = () => ({ status: 1, stdout: "", stderr: "fixture failure" });

childProcess.spawnSync = (command, args, options = {}) => {
  appendFileSync(trace, `${JSON.stringify({ command, args })}\n`);
  if (command === process.execPath && args[0] === "scripts/ci/check-cnb-release-evidence.mjs") return original(command, args, options);
  if (command === "git") {
    if (args[0] === "rev-parse") return ok(request.test_commit);
    if (args[0] === "merge-base") return ok();
    if (args[0] === "diff") return ok(mode === "stale-app" ? "apps/admin/src/app.tsx\0" : "");
  }
  if (command === "gh") {
    if (mode.startsWith("preflight-")) {
      if (args[0] === "api") return ok({ event: "workflow_dispatch", conclusion: mode === "preflight-failed-run" ? "failure" : "success",
        path: ".github/workflows/validate-candidate-images.yml", head_branch: "main", run_attempt: 1, head_sha: request.test_commit,
        head_repository: { full_name: "jinmozhe/pinjie-mall" } });
      const directory = args[args.indexOf("--dir") + 1];
      mkdirSync(directory, { recursive: true });
      writeFileSync(resolve(directory, "deployment-composition.json"), readFileSync(resolve(process.env.RUNNER_TEMP, "trusted.json")));
      return ok();
    }
    if (args[0] === "api") return ok({ event: "workflow_dispatch", conclusion: mode === "source-error" ? "failure" : "success",
      path: ".github/workflows/publish-images.yml", head_branch: "main", run_attempt: 1,
      head_repository: { full_name: "jinmozhe/pinjie-mall" } });
    if (args[0] === "run" && args[1] === "download") {
      const directory = args[args.indexOf("--dir") + 1];
      mkdirSync(directory, { recursive: true });
      writeFileSync(resolve(directory, "handoff.json"), JSON.stringify({ schema: "pinjie-source-handoff-v1", commit_sha: request.test_commit,
        mode: "fast", reason: "fixture decision", full_validation_run_id: "", run_id: "123", run_attempt: "1" }));
      return ok();
    }
  }
  if (command === "docker") {
    if (args[0] === "buildx") {
      if (args.includes("--raw")) return ok({ manifests: [{ annotations: { "vnd.docker.reference.type": "attestation-manifest" } }] });
      const app = ["backend", "admin"].find((name) => args[3].includes(`pinjie-mall-${name}:`));
      return ok({ digest: mode === "wrong-digest" ? `sha256:${"f".repeat(64)}` : request.images[app].release.image.digest });
    }
    if (args[0] === "pull") return ok();
    if (args[0] === "image") return ok([{ Architecture: "amd64", Os: "linux", Config: { Labels: {
      "org.opencontainers.image.revision": request.test_commit,
      "org.opencontainers.image.source": "https://github.com/jinmozhe/pinjie-mall",
    } } }]);
    if (args[0] === "compose") {
      const config = JSON.parse(readFileSync(args[args.indexOf("--file") + 1], "utf8"));
      assert.equal(config.services.backend.environment.ENVIRONMENT, "test");
      assert.match(config.services.backend.environment.DATABASE_URL, /@postgres:5432\/pinjie_candidate_test$/u);
      assert.equal(config.networks, undefined);
      for (const app of ["backend", "admin"]) assert.equal(config.services[app].image, request.images[app].release.image.reference);
      if (args.includes("down") && mode === "cleanup-error") return fail();
      return ok();
    }
  }
  if (command === process.execPath && args[0] === "node_modules/@playwright/test/cli.js") {
    assert.equal(options.env.E2E_MANAGED_SERVERS, "1");
    const status = mode === "browser-error" ? "failed" : "passed";
    const projects = mode === "partial-browser" ? ["admin-desktop"] : ["admin-desktop", "admin-mobile"];
    writeFileSync(resolve(options.env.E2E_SUMMARY_DIR, "e2e-summary.json"), JSON.stringify({ status,
      tests: projects.map((project) => ({ project, status })) }));
    return status === "passed" ? ok() : fail();
  }
  throw new Error(`Unexpected subprocess in isolated fixture: ${command}`);
};
syncBuiltinESMExports();
