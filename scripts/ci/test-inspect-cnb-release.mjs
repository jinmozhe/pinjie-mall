import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import YAML from "yaml";
import { inspectRelease, renderReleaseSummary } from "./inspect-cnb-release.mjs";

const hostileReports = [{ stage: '</pre><script>alert("fixture")</script>',
  markdown: "```\n# injected heading\n~~~\n[link](https://example.com)", entities: "&lt;tag&gt;" }];
const summaryLines = renderReleaseSummary(hostileReports).trimEnd().split("\n");
assert(summaryLines[0].includes("does not verify release success"));
assert.equal(summaryLines[1], "");
assert(summaryLines.slice(2).every(line => line.startsWith("    ")), "Remote data must remain entirely inside indented code");
assert.deepEqual(JSON.parse(summaryLines.slice(2).map(line => line.slice(4)).join("\n")), hostileReports, "Literal summary must preserve the complete report");

const sha = "a".repeat(40);
const token = "fixture-private-token";
const repository = "pjwl/pinjie-mall";
const build = { sha, slug: repository, sn: "cnb-fixture-1", event: "push" };
const history = { data: [build], total: 1 };
const status = {
  status: "error",
  pipelinesStatus: Object.fromEntries(["backend", "admin"].map((name, index) => [name, {
    id: `pipeline-${index}`, name: `${name}-image`, status: index ? "skipped" : "error",
    stages: [{ id: "stage-1", name: "Build and push run-unique candidate", status: index ? "skipped" : "error" }],
  }])),
};
const failure = { error: "denied: no permission", content: [
  "exporting cache failed", "password=not-a-real-password", token, "::warning::untrusted",
] };
function fixture(replies) {
  const calls = [];
  return {
    calls,
    fetchImpl: async (url, options) => {
      assert(url.startsWith(`https://api.cnb.cool/${repository}/-/build/`));
      assert.equal(options.method, "GET");
      assert.equal(options.redirect, "error");
      assert.equal(options.headers.Authorization, `Bearer ${token}`);
      assert(options.signal instanceof AbortSignal);
      calls.push(url);
      assert(replies.length, "Unexpected extra request");
      const value = replies.shift();
      if (value.http) return { ok: false, status: value.http, json: () => { throw Error("Do not read error body"); } };
      if (value.invalidJson) return { ok: true, json: () => { throw Error("secret-response-body"); } };
      return { ok: true, json: async () => structuredClone(value) };
    },
  };
}
const run = (mock, extra = {}) => inspectRelease({ sha, token, fetchImpl: mock.fetchImpl, ...extra });
const complete = fixture([history, status, failure]);
const report = await run(complete);
assert.equal(complete.calls.length, 3);
assert.equal(report[0].status, "error");
assert.equal(report[0].pipelines[1].status, "skipped");
assert.deepEqual(report[0].failureDetails[0].categories, ["registry-authorization", "registry-cache"]);
for (const secret of [token, "not-a-real-password", "::warning::"]) assert(!JSON.stringify(report).includes(secret));
const successful = structuredClone(status);
successful.status = "success";
for (const pipeline of Object.values(successful.pipelinesStatus)) {
  pipeline.status = "success"; pipeline.stages[0].status = "success";
}
assert.equal((await run(fixture([history, successful])))[0].failureDetails.length, 0);
for (const http of [401, 403, 302, 500]) await assert.rejects(run(fixture([{ http }])), new RegExp(`HTTP ${http}`));
await assert.rejects(run(fixture([{ invalidJson: true }])), /Invalid CNB JSON/);
await assert.rejects(run(fixture([[]])), /response shape/);
await assert.rejects(run(fixture([{ data: { data: [], total: 0 } }])), /response shape/);
await assert.rejects(run(fixture([{ data: [], total: 0 }])), /No CNB builds/);
await assert.rejects(run(fixture([{ data: [], total: 1 }])), /Incomplete/);
await assert.rejects(run(fixture([{ data: [build, build], total: 2 }])), /duplicate/);
await assert.rejects(run(fixture([{ data: [build], total: 0 }])), /Inconsistent/);
for (const change of [{ sha: "b".repeat(40) }, { slug: "pjwl/other" }, { sn: "../other" }]) {
  const mock = fixture([{ data: [{ ...build, ...change }], total: 1 }]);
  await assert.rejects(run(mock), /identity/);
  assert.equal(mock.calls.length, 1);
}
await assert.rejects(run(fixture([history, { data: status }])), /Missing CNB pipeline/);
await assert.rejects(run(fixture([history, status, { error: "secret", content: [7] }])), /failure stage/);
const bad = structuredClone(status); bad.pipelinesStatus.backend.name = token;
await assert.rejects(run(fixture([history, bad])), /Invalid CNB pipeline/);
const injected = structuredClone(status); injected.pipelinesStatus.backend.stages[0].name = "oops\n::error::";
await assert.rejects(run(fixture([history, injected])), /status field/);
const emptyStages = structuredClone(status); emptyStages.pipelinesStatus.backend.stages = [];
await assert.rejects(run(fixture([history, emptyStages])), /Invalid CNB pipeline/);
const duplicates = structuredClone(status); duplicates.pipelinesStatus.copy = duplicates.pipelinesStatus.backend;
await assert.rejects(run(fixture([history, duplicates])), /duplicate pipelines/);
const oversized = { data: [], total: 2001 };
await assert.rejects(run(fixture([oversized])), /response shape/);
const manyBuilds = Array.from({ length: 200 }, (_, index) => ({ ...build, sn: `cnb-fixture-${index}` }));
const bounded = fixture([{ data: manyBuilds.slice(0, 100), total: 200 }, { data: manyBuilds.slice(100), total: 200 },
  ...Array.from({ length: 198 }, () => successful)]);
await assert.rejects(run(bounded), /request limit/);
assert.equal(bounded.calls.length, 200);
const noCalls = fixture([]);
await assert.rejects(run(noCalls, { sha: "main" }), /invalid source SHA/);
await assert.rejects(run(noCalls, { token: "" }), /credential/);
assert.equal(noCalls.calls.length, 0);
const second = { ...build, sn: "cnb-fixture-2" };
const pagination = fixture([{ data: [build], total: 2 }, { data: [second], total: 2 }, successful, successful]);
assert.equal((await run(pagination)).length, 2);
assert(pagination.calls[1].includes("page=2"));
const workflow = YAML.parse(readFileSync(".github/workflows/inspect-cnb-release.yml", "utf8"));
assert.deepEqual(Object.keys(workflow.on), ["workflow_dispatch"]);
assert.deepEqual(workflow.permissions, { contents: "read" });
assert.equal(workflow.jobs.inspect.environment, "cnb-source-handoff");
const steps = workflow.jobs.inspect.steps;
assert(steps[0].run.includes('test "$GITHUB_REPOSITORY" = "jinmozhe/pinjie-mall"'));
assert(steps[0].run.includes('test "$GITHUB_REF" = "refs/heads/$DEFAULT_BRANCH"'));
assert(steps[0].run.includes('https://cnb.cool/pjwl/pinjie-mall'));
assert.equal(steps[1].with["persist-credentials"], false);
assert.equal(steps.at(-1).run, "node scripts/ci/inspect-cnb-release.mjs");
assert(!readFileSync(".github/workflows/inspect-cnb-release.yml", "utf8").includes("TCR_PUBLISH_PASSWORD"));
console.log("CNB read-only diagnostic regression checks passed.");
