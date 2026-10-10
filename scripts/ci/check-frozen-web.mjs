import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
let root = path.resolve(import.meta.dirname, "../..");
let base;
const seen = new Set();
for (let index = 0; index < args.length; index += 2) {
  const value = args[index + 1];
  if (!value) throw new Error(`Missing value for ${args[index]}`);
  if (seen.has(args[index])) throw new Error(`Duplicate option: ${args[index]}`);
  seen.add(args[index]);
  if (args[index] === "--base") base = value;
  else if (args[index] === "--root") root = path.resolve(value);
  else throw new Error(`Unsupported or duplicate option: ${args[index]}`);
}

const git = (...parameters) => execFileSync("git", parameters, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
if (base === undefined) base = git("merge-base", "origin/main", "HEAD");
if (!/^[0-9a-f]{40}$/u.test(base) || /^0+$/u.test(base)) throw new Error("Frozen Web requires a full nonzero Git commit SHA.");
if (git("cat-file", "-t", base) !== "commit") throw new Error("Frozen Web base must be an existing commit.");

const protectedPaths = ["apps/web", ":(exclude)apps/web/AGENTS.md", "scripts/disabled-web.mjs"];
// Include staged and unstaged edits, not only committed changes. Rule updates
// may change AGENTS.md; frozen business code and runtime entry points may not.
const changes = git("diff", "--no-ext-diff", "--no-textconv", "--name-only", base, "--", ...protectedPaths);
const untracked = git("ls-files", "--others", "--exclude-standard", "--", ...protectedPaths);
if (changes || untracked) throw new Error(`Frozen Web files changed: ${[changes, untracked].filter(Boolean).join("\n")}`);

const web = JSON.parse(readFileSync(path.join(root, "apps/web/package.json"), "utf8"));
for (const command of ["dev", "build", "start", "test"]) {
  if (web.scripts?.[command] !== "node ../../scripts/disabled-web.mjs") {
    throw new Error(`Frozen Web command ${command} must remain disabled.`);
  }
}
const disabled = readFileSync(path.join(root, "scripts/disabled-web.mjs"), "utf8").trim();
const expected = 'throw new Error("apps/web is permanently frozen in pinjie-mall. Use Backend and Admin; the consumer application will be a WeChat mini program.");';
if (disabled !== expected) throw new Error("Frozen Web disabled entry point must fail explicitly.");

console.log("Frozen Web isolation passed: code unchanged and runtime commands disabled; no Web application typecheck or runtime executed.");
