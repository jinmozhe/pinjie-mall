import { readFile } from "node:fs/promises";
import yaml from "yaml";

const document = yaml.parse(await readFile(".cnb.yml", "utf8"), { merge: true });
const push = document.main?.push;
const fullRelease = document.main?.web_trigger_full_release;

const common = [
  ".dockerignore",
  ".cnb.yml",
  "scripts/ci/cnb-*.sh",
  "scripts/ci/*cnb*evidence*.mjs",
];
const frontendShared = [
  "package.json",
  "pnpm-lock.yaml",
  "pnpm-workspace.yaml",
  ".pnpmfile.cjs",
  "packages/**",
  "patches/**",
];
const expectedRoutes = {
  "backend-image": ["apps/backend/**", ...common],
  "admin-image": ["apps/admin/**", "apps/web/package.json", ...frontendShared, ...common],
};

function routeMatches(route, file) {
  if (route.endsWith("/**")) {
    return file.startsWith(route.slice(0, -2));
  }
  if (route === "scripts/ci/cnb-*.sh") {
    const basename = file.slice("scripts/ci/".length);
    return file.startsWith("scripts/ci/cnb-") && basename.endsWith(".sh") && !basename.includes("/");
  }
  if (route === "scripts/ci/*cnb*evidence*.mjs") {
    const basename = file.slice("scripts/ci/".length);
    const cnbIndex = basename.indexOf("cnb");
    return (
      file.startsWith("scripts/ci/") &&
      basename.endsWith(".mjs") &&
      !basename.includes("/") &&
      cnbIndex >= 0 &&
      basename.indexOf("evidence", cnbIndex + 3) >= 0
    );
  }
  return route === file;
}

function selectedPipelines(file) {
  return Object.entries(expectedRoutes)
    .filter(([, routes]) => routes.some((route) => routeMatches(route, file)))
    .map(([pipeline]) => pipeline)
    .sort();
}

function requireCondition(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

requireCondition(push && typeof push === "object", "main.push must contain named pipelines.");
requireCondition(fullRelease && typeof fullRelease === "object", "The controlled full-release event is missing.");
requireCondition(
  JSON.stringify(Object.keys(push).sort()) === JSON.stringify(Object.keys(expectedRoutes).sort()),
  "main.push must contain exactly the two image pipelines.",
);

for (const [pipelineName, routes] of Object.entries(expectedRoutes)) {
  const pipeline = push[pipelineName];
  requireCondition(pipeline?.name === pipelineName, `${pipelineName} must preserve its pipeline name.`);
  requireCondition(
    JSON.stringify(pipeline.ifModify) === JSON.stringify(routes),
    `${pipelineName} ifModify routes drifted from the Docker build-input contract.`,
  );
  const imageKey = pipelineName.replace("-image", "");
  requireCondition(pipeline.env?.IMAGE_KEY === imageKey, `${pipelineName} IMAGE_KEY is incorrect.`);
  requireCondition(pipeline.env?.RELEASE_PIPELINE === pipelineName, `${pipelineName} release identity is incorrect.`);
  requireCondition(
    pipeline.env?.EVIDENCE_ROOT === `.cnb/evidence/${imageKey}`,
    `${pipelineName} evidence path is not isolated.`,
  );
  requireCondition(
    pipeline.env?.DOCKER_CONFIG === `/tmp/pinjie-cnb-docker-config-${imageKey}`,
    `${pipelineName} Docker credentials are not isolated.`,
  );
  requireCondition(fullRelease[pipelineName]?.env?.IMAGE_KEY === imageKey, `${pipelineName} is missing from full release.`);
  requireCondition(!Object.hasOwn(fullRelease[pipelineName], "ifModify"), `${pipelineName} full release must ignore path filters.`);
}

const routingFixtures = {
  "apps/backend/app/main.py": ["backend-image"],
  "apps/web/src/app/page.tsx": [],
  "apps/admin/src/app.tsx": ["admin-image"],
  "apps/web/package.json": ["admin-image"],
  "apps/admin/package.json": ["admin-image"],
  "package.json": ["admin-image"],
  "packages/api-client/src/index.ts": ["admin-image"],
  ".dockerignore": ["admin-image", "backend-image"],
  ".cnb.yml": ["admin-image", "backend-image"],
  "scripts/ci/cnb-publish-images.sh": ["admin-image", "backend-image"],
  "scripts/ci/create-cnb-release-evidence.mjs": ["admin-image", "backend-image"],
  "scripts/ci/nested/cnb-publish-images.sh": [],
  "compose.prod.yml": [],
  "docs/operations/container-build-and-run.md": [],
  "plans/2026-09-04_fixture.md": [],
};
for (const [file, expected] of Object.entries(routingFixtures)) {
  requireCondition(
    JSON.stringify(selectedPipelines(file)) === JSON.stringify(expected),
    `${file} selected an unexpected image pipeline set.`,
  );
}

const buttonDocument = yaml.parse(await readFile(".cnb/web_trigger.yml", "utf8"));
const branchRule = buttonDocument.branch?.[0];
requireCondition(branchRule?.reg === "^main$", "The full-release button must be restricted to main.");
requireCondition(branchRule.buttons?.length === 1, "Exactly one full-release button is expected.");
requireCondition(
  branchRule.buttons[0].event === "web_trigger_full_release",
  "The full-release button event does not match .cnb.yml.",
);

console.log("CNB change-routing and controlled full-release fixtures passed.");
