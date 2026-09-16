import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export function filterScan(report) {
  if (report?.SchemaVersion !== 2 || report.ArtifactType !== "container_image" ||
      !Array.isArray(report.Results) || report.Results.length === 0) {
    throw new Error("Missing or malformed container scan results.");
  }
  let packages = 0;
  const filtered = structuredClone(report);
  for (const result of filtered.Results) {
    if (typeof result.Target !== "string" || !["os-pkgs", "lang-pkgs"].includes(result.Class) ||
        !Array.isArray(result.Packages) ||
        (result.Vulnerabilities !== undefined && !Array.isArray(result.Vulnerabilities))) {
      throw new Error("Malformed package or vulnerability results.");
    }
    packages += result.Packages.length;
    result.Vulnerabilities = (result.Vulnerabilities ?? []).filter((item) => {
      if (typeof item.VulnerabilityID !== "string" ||
          !["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(item.Severity) ||
          (item.FixedVersion !== undefined && typeof item.FixedVersion !== "string")) {
        throw new Error("Malformed vulnerability evidence.");
      }
      return ["HIGH", "CRITICAL"].includes(item.Severity) && Boolean(item.FixedVersion?.trim());
    });
  }
  if (packages === 0) throw new Error("Container package inventory is empty.");
  return filtered;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const key = process.env.IMAGE_KEY;
  const root = process.env.EVIDENCE_ROOT;
  if (!["backend", "admin"].includes(key) || root !== `.cnb/evidence/${key}`) {
    throw new Error("Invalid scan evidence scope.");
  }
  try {
    const report = filterScan(JSON.parse(await readFile(`${root}/${key}-trivy-full.json`, "utf8")));
    await writeFile(`${root}/${key}-trivy.json`, `${JSON.stringify(report)}\n`);
    const blocked = report.Results.flatMap((result) => result.Vulnerabilities);
    if (blocked.length) {
      // Vulnerability identifiers and package versions are public scan metadata.
      throw new Error(blocked.map((v) => `${v.VulnerabilityID} ${v.Severity} ${v.FixedVersion}`).join("\n"));
    }
    console.log(`${key}: fixed HIGH/CRITICAL gate passed; complete inventory retained.`);
  } catch (error) {
    await writeFile(`${root}/scan-failure-summary.txt`, `image=${key}\nphase=structured-vulnerability-gate\n${error.message}\n`);
    throw error;
  }
}
