import { appendFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export async function inspectRelease({ sha, token, fetchImpl = fetch }) {
  const repository = 'pjwl/pinjie-mall';
  if (typeof token !== 'string' || !token.trim() || typeof sha !== 'string' || !/^[0-9a-f]{40}$/.test(sha)) {
    throw new Error('Missing CNB credential or invalid source SHA.');
  }
  let requestCount = 0;
  const overallTimeout = AbortSignal.timeout(240000);
  async function read(path) {
    if (++requestCount > 200) throw new Error('CNB request limit exceeded.');
    const response = await fetchImpl(`https://api.cnb.cool/${repository}/-/build/${path}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.cnb.api+json' },
      redirect: 'error',
      signal: AbortSignal.any([overallTimeout, AbortSignal.timeout(30000)]),
    });
    if (!response.ok) {
      throw new Error(`CNB query returned HTTP ${response.status}; requires repo-cnb-history:r and repo-cnb-trigger:r on ${repository}.`);
    }
    try { return await response.json(); } catch { throw new Error('Invalid CNB JSON response.'); }
  }
  // CNB OpenAPI dto.BuildLogsResult: { data: LogInfo[], total: integer }.
  function buildHistory(payload) {
    if (!payload || !Array.isArray(payload.data) || !Number.isInteger(payload.total) ||
        payload.total < 0 || payload.data.length > 100 || payload.total > 2000) {
      throw new Error('Invalid CNB build history response shape.');
    }
    return payload;
  }
  function failureCategories(stageDetail) {
    // Report fixed categories only: arbitrary remote log text may contain TCR secrets.
    if (!stageDetail || !Array.isArray(stageDetail.content) ||
        stageDetail.content.some(line => typeof line !== 'string') ||
        (stageDetail.error !== undefined && typeof stageDetail.error !== 'string')) {
      throw new Error('Invalid CNB failure stage response.');
    }
    const lines = [stageDetail.error, ...stageDetail.content];
    const content = lines.filter(line => typeof line === 'string').join('\n');
    const rules = [
      ['registry-authorization', /unauthorized|no permission|failed to authorize|denied/i],
      ['registry-cache', /exporting cache|cache exporter|importing cache/i],
      ['vulnerability-gate', /CVE-\d{4}-\d+|HIGH|CRITICAL/i],
      ['network-or-timeout', /timeout|timed out|ECONNRESET|ENOTFOUND|TLS handshake/i],
      ['evidence-validation', /digest mismatch|missing provenance|missing an attestation|labels do not match/i],
    ];
    const categories = rules.filter(([, pattern]) => pattern.test(content)).map(([name]) => name);
    return categories.length ? categories : ['inspect-failed-stage-in-cnb'];
  }
  function safeField(value) {
    if (typeof value !== 'string' || !value.trim() || value.length > 160 || /[\r\n\x00-\x1f]/u.test(value) || value.includes(token)) {
      throw new Error('Invalid CNB status field.');
    }
    return value;
  }
  const builds = [];
  const seenBuilds = new Set();
  for (let page = 1; ; page++) {
    if (page > 20) throw new Error('Build history exceeds bounded query limit.');
    const result = buildHistory(await read(`logs?sha=${sha}&page=${page}&page_size=100`));
    for (const build of result.data) {
      if (!build || typeof build.sn !== 'string' || seenBuilds.has(build.sn)) {
        throw new Error('Invalid or duplicate CNB build identity.');
      }
      seenBuilds.add(build.sn);
      builds.push(build);
    }
    if (builds.length > result.total) throw new Error('Inconsistent CNB build history total.');
    if (builds.length >= result.total) break;
    if (result.data.length === 0) throw new Error('Incomplete CNB build history.');
  }
  if (builds.length === 0) throw new Error('No CNB builds found for the requested source SHA.');
  const reports = [];
  for (const build of builds) {
    if (build.sha !== sha || build.slug !== repository || !/^[a-zA-Z0-9_-]{1,100}$/.test(build.sn)) {
      throw new Error('CNB build identity does not match the requested release.');
    }
    const detail = await read(`status/${encodeURIComponent(build.sn)}`);
    if (!detail || !detail.pipelinesStatus || typeof detail.pipelinesStatus !== 'object' || Array.isArray(detail.pipelinesStatus)) {
      throw new Error('Missing CNB pipeline status.');
    }
    const pipelines = Object.values(detail.pipelinesStatus).map(pipeline => {
      if (!pipeline || !Array.isArray(pipeline.stages) || pipeline.stages.length === 0 || pipeline.stages.length > 100 ||
          !['backend-image', 'admin-image'].includes(pipeline.name)) {
        throw new Error('Invalid CNB pipeline or stage status.');
      }
      return {
        id: safeField(pipeline.id), name: safeField(pipeline.name), status: safeField(pipeline.status),
        stages: pipeline.stages.map(({ id, name, status }) => ({ id: safeField(id), name: safeField(name), status: safeField(status) })),
      };
    });
    if (pipelines.length === 0 || new Set(pipelines.map(pipeline => pipeline.name)).size !== pipelines.length) {
      throw new Error('CNB returned missing or duplicate pipelines.');
    }
    const failureDetails = [];
    for (const pipeline of pipelines) {
      for (const stage of pipeline.stages.filter(candidate => candidate.status === 'error')) {
        const stageDetail = await read(`logs/stage/${encodeURIComponent(build.sn)}/${encodeURIComponent(pipeline.id)}/${encodeURIComponent(stage.id)}`);
        failureDetails.push({
          pipeline: pipeline.name,
          stage: stage.name,
          categories: failureCategories(stageDetail),
        });
      }
    }
    reports.push({ sha, sn: build.sn, event: safeField(build.event), status: safeField(detail.status), pipelines, failureDetails });
  }
  return reports;
}

export function renderReleaseSummary(reports) {
  // GFM indented code keeps remote HTML and Markdown literal without HTML sanitization.
  const codeBlock = JSON.stringify(reports, null, 2).split('\n').map(line => '    ' + line).join('\n');
  return 'CNB status query completed. This does not verify release success or TCR image existence.\n\n' + codeBlock + '\n';
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const reports = await inspectRelease({ sha: process.env.COMMIT_SHA, token: process.env.CNB_PUSH_TOKEN });
    const output = JSON.stringify(reports, null, 2);
    // All console lines have a prefix so remote fields cannot become workflow commands.
    console.log(output.split('\n').map(line => 'CNB: ' + line).join('\n'));
    if (process.env.GITHUB_STEP_SUMMARY) {
      appendFileSync(process.env.GITHUB_STEP_SUMMARY, renderReleaseSummary(reports));
    }
  } catch (error) {
    // Do not forward response bodies, request objects, or chained fetch errors.
    const message = String(error.message).replaceAll(process.env.CNB_PUSH_TOKEN || '__unused__', '[REDACTED]');
    console.error('CNB inspection failed: ' + message.replace(/[\r\n]/g, ' '));
    process.exitCode = 1;
  }
}
