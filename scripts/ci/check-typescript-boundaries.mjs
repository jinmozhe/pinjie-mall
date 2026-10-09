import { createRequire } from "node:module";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, relative, resolve, sep } from "node:path";

const toolRoot = resolve(import.meta.dirname, "..", "..");
const requireFromWeb = createRequire(resolve(toolRoot, "apps", "web", "package.json"));
const ts = requireFromWeb("typescript");

const rootArgumentIndex = process.argv.indexOf("--root");
const workspaceRoot = resolve(rootArgumentIndex >= 0 ? process.argv[rootArgumentIndex + 1] : toolRoot);
const sourceExtensions = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]);
const ignoredDirectories = new Set(["node_modules", ".next", ".umi", ".umi-production", "dist", "coverage"]);
const indexNames = new Set(["index.ts", "index.tsx", "index.js", "index.jsx", "index.mjs", "index.cjs"]);
const violations = [];

function toForwardSlash(path) {
  return path.split(sep).join("/");
}

function relativePath(path) {
  return toForwardSlash(relative(workspaceRoot, path));
}

function isWithin(path, parent) {
  const pathFromParent = relative(parent, path);
  return pathFromParent === "" || (!pathFromParent.startsWith("..") && !pathFromParent.includes(`..${sep}`));
}

function collectSourceFiles(root) {
  if (!existsSync(root)) return [];
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!ignoredDirectories.has(entry.name)) files.push(...collectSourceFiles(resolve(root, entry.name)));
      continue;
    }
    const path = resolve(root, entry.name);
    if (entry.isFile() && sourceExtensions.has(extname(path)) && !path.endsWith(".d.ts")) files.push(path);
  }
  return files;
}

function resolveSourcePath(candidate) {
  const candidates = [candidate];
  for (const extension of sourceExtensions) candidates.push(`${candidate}${extension}`);
  for (const indexName of indexNames) candidates.push(resolve(candidate, indexName));
  return candidates.find((path) => existsSync(path) && statSync(path).isFile());
}

function importSpecifiers(sourceFile) {
  const imports = [];
  function record(node, value) {
    const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
    const typeOnly = ts.isImportDeclaration(node) ? node.importClause?.isTypeOnly === true : ts.isExportDeclaration(node) && node.isTypeOnly;
    imports.push({ value, line: position.line + 1, typeOnly });
  }
  function visit(node) {
    if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
      if (ts.isStringLiteralLike(node.moduleSpecifier)) record(node, node.moduleSpecifier.text);
    } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
      const expression = node.moduleReference.expression;
      if (expression && ts.isStringLiteralLike(expression)) record(node, expression.text);
    } else if (ts.isCallExpression(node) && node.arguments.length === 1 && ts.isStringLiteralLike(node.arguments[0])) {
      if (node.expression.kind === ts.SyntaxKind.ImportKeyword) record(node, node.arguments[0].text);
      if (ts.isIdentifier(node.expression) && node.expression.text === "require") record(node, node.arguments[0].text);
    }
    ts.forEachChild(node, visit);
  }
  visit(sourceFile);
  return imports;
}

function featureName(path, featuresRoot) {
  if (!isWithin(path, featuresRoot)) return undefined;
  const parts = relative(featuresRoot, path).split(sep);
  return parts.length > 1 ? parts[0] : undefined;
}

function checkApplication(name) {
  const appRoot = resolve(workspaceRoot, "apps", name);
  const sourceRoot = resolve(appRoot, "src");
  const featuresRoot = resolve(sourceRoot, "features");
  const files = collectSourceFiles(sourceRoot);
  const fileSet = new Set(files.map((path) => path.toLowerCase()));
  const graph = new Map(files.map((path) => [path, []]));
  let edgeCount = 0;

  for (const file of files) {
    const sourceText = readFileSync(file, "utf8");
    const kind = file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
    const sourceFile = ts.createSourceFile(file, sourceText, ts.ScriptTarget.Latest, true, kind);
    for (const specifier of importSpecifiers(sourceFile)) {
      if (name === "miniapp" && /^@pinjie\/api-client(?:\/|$)/.test(specifier.value) && !specifier.typeOnly) {
        violations.push(`${relativePath(file)}:${specifier.line}: Miniapp must consume generated API contracts with import type, without the browser SDK runtime.`);
      }
      for (const otherName of ["admin", "web", "miniapp", "backend"].filter((candidate) => candidate !== name)) {
        if (specifier.value.includes(`apps/${otherName}/`) || specifier.value === `@pinjie/${otherName}`) {
          violations.push(`${relativePath(file)}:${specifier.line}: Application ${name} must not import application ${otherName}.`);
        }
      }

      if (name === "miniapp" && relativePath(file).includes("/domain/") && /^(react(?:\/|$)|@tarojs\/|@nutui\/|@tanstack\/|node:|(?:fs|http|https|net|child_process|axios)(?:\/|$))/.test(specifier.value)) {
        violations.push(`${relativePath(file)}:${specifier.line}: Miniapp domain must remain independent of UI, platform and I/O.`);
      }
      let candidate;
      if (specifier.value.startsWith("@/")) candidate = resolve(sourceRoot, specifier.value.slice(2));
      if (specifier.value.startsWith(".")) candidate = resolve(dirname(file), specifier.value);
      if (!candidate) continue;

      const target = resolveSourcePath(candidate);
      if (!target) continue;
      for (const otherName of ["admin", "web", "miniapp", "backend"].filter((item) => item !== name)) {
        if (isWithin(target, resolve(workspaceRoot, "apps", otherName))) {
          violations.push(`${relativePath(file)}:${specifier.line}: Application ${name} must not import application ${otherName}.`);
        }
      }
      if (!fileSet.has(target.toLowerCase())) continue;

      graph.get(file).push(target);
      edgeCount += 1;
      const sourceFeature = featureName(file, featuresRoot);
      const targetFeature = featureName(target, featuresRoot);
      if (name === "miniapp" && relativePath(file).includes("/domain/") && !relativePath(target).includes("/domain/")) {
        violations.push(`${relativePath(file)}:${specifier.line}: Miniapp domain must not import application infrastructure or UI.`);
      }
      if (name === "miniapp" && !sourceFeature && targetFeature && !indexNames.has(target.split(sep).at(-1))) {
        violations.push(`${relativePath(file)}:${specifier.line}: Miniapp pages and infrastructure must use Feature public entries.`);
      }
      if (sourceFeature && targetFeature && sourceFeature !== targetFeature && !indexNames.has(target.split(sep).at(-1))) {
        violations.push(
          `${relativePath(file)}:${specifier.line}: Feature ${sourceFeature} must import Feature ${targetFeature} through its public index.`,
        );
      }
    }
  }

  const visiting = new Set();
  const visited = new Set();
  const stack = [];
  const reportedCycles = new Set();
  function visit(file) {
    if (visited.has(file)) return;
    visiting.add(file);
    stack.push(file);
    for (const target of graph.get(file) ?? []) {
      if (visiting.has(target)) {
        const start = stack.indexOf(target);
        const cycle = [...stack.slice(start), target].map(relativePath);
        const key = [...new Set(cycle.slice(0, -1))].toSorted().join("|");
        if (!reportedCycles.has(key)) {
          reportedCycles.add(key);
          violations.push(`${cycle[0]}:1: Circular TypeScript dependency: ${cycle.join(" -> ")}.`);
        }
      } else {
        visit(target);
      }
    }
    stack.pop();
    visiting.delete(file);
    visited.add(file);
  }
  for (const file of files) visit(file);
  return { files: files.length, edges: edgeCount };
}

const totals = [checkApplication("admin"), checkApplication("web"), checkApplication("miniapp")].reduce(
  (sum, result) => ({ files: sum.files + result.files, edges: sum.edges + result.edges }),
  { files: 0, edges: 0 },
);

if (violations.length > 0) {
  for (const violation of violations.toSorted()) console.error(violation);
  process.exit(1);
}

console.log(`TypeScript dependency graph checks passed for ${totals.files} files and ${totals.edges} edges.`);
