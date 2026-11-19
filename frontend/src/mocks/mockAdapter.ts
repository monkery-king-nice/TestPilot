// 内置 Mock 适配层：在前后端未联调前，用同一份 RunDetail 示例模拟真实 API 行为。
// - 与真实 API 同签名（见 src/api/runs.ts），联调时通过 VITE_USE_MOCK=false 切换。
// - 环境配置保存在内存，运行进度按时间推进（QUEUED → RUNNING → COMPLETED），用于演示轮询。

import type {
  Analysis,
  Case,
  EnvironmentRead,
  EnvironmentWrite,
  RunDetail,
  RunTarget,
  StartRunRequest,
  StartRunResponse
} from '@/api/types'
import { sampleConfirmedCases, sampleAnalysisMap, sampleRunDetailByStatus, sampleRunDetail } from './runDetail.samples'

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** 模拟网络往返延迟 */
const LATENCY = 250

/** 内存环境配置：只保存非敏感目标与字段名（值仅服务端执行器可见） */
const mockEnvironment = {
  target: 'demo' as 'demo' | 'local',
  service_id: 'demo' as string | null,
  base_url: 'http://127.0.0.1:8010' as string | null,
  environment_version: 1 as number | null,
  configured_keys: ['password', 'username'] as string[]
}

/** 运行进度：runId -> 启动时间戳 */
const runStartTimes = new Map<string, number>()

/** 单个项目（演示只用一个 project_id） */
const DEMO_PROJECT_ID = 'proj-demo-0001'

/** 当前内存环境对应的执行目标（运行批次创建时冻结）。 */
function currentTarget(): RunTarget {
  return {
    kind: mockEnvironment.target,
    service_id: mockEnvironment.service_id ?? 'demo',
    base_url: mockEnvironment.base_url ?? 'http://127.0.0.1:8010',
    environment_version: mockEnvironment.environment_version
  }
}

export async function mockGetEnvironment(projectId: string): Promise<EnvironmentRead> {
  await delay(LATENCY)
  void projectId
  return { ...mockEnvironment, configured_keys: [...mockEnvironment.configured_keys] }
}

export async function mockPutEnvironment(projectId: string, write: EnvironmentWrite): Promise<EnvironmentRead> {
  await delay(LATENCY)
  void projectId
  mockEnvironment.target = write.target
  mockEnvironment.service_id = write.target === 'local' ? (write.service_id ?? null) : 'demo'
  mockEnvironment.base_url = write.target === 'local' ? (write.base_url ?? null) : 'http://127.0.0.1:8010'
  mockEnvironment.environment_version = (mockEnvironment.environment_version ?? 0) + 1
  mockEnvironment.configured_keys = Object.keys(write.secrets ?? {}).sort()
  return { ...mockEnvironment, configured_keys: [...mockEnvironment.configured_keys] }
}

export async function mockGetCases(projectId: string): Promise<Case[]> {
  await delay(LATENCY)
  void projectId
  // 只展示已确认用例（CONFIRMED）
  return sampleConfirmedCases.filter((c) => c.status === 'CONFIRMED')
}

export async function mockStartRun(projectId: string, req: StartRunRequest): Promise<StartRunResponse> {
  await delay(LATENCY)
  void projectId
  const runId = `run-demo-${Date.now().toString(36)}`
  runStartTimes.set(runId, Date.now())
  void req
  return { run_id: runId, status: 'QUEUED' }
}

export async function mockGetRunDetail(projectId: string, runId: string): Promise<RunDetail> {
  await delay(LATENCY)
  void projectId

  // 固定样例 run-demo-0001 代表一个「已完成的历史批次」，用于直接查看终态与刷新恢复。
  if (runId === 'run-demo-0001') {
    return JSON.parse(JSON.stringify(sampleRunDetail)) as RunDetail
  }

  const startedAt = runStartTimes.get(runId) ?? Date.now()
  const elapsed = Date.now() - startedAt

  // 按时间推进状态，演示轮询与刷新恢复。
  let detail: RunDetail
  if (elapsed < 900) {
    detail = {
      run_id: runId,
      status: 'QUEUED',
      target: currentTarget(),
      counts: { PASS: 0, FAIL: 0, ERROR: 0, BLOCKED: 0 },
      results: []
    }
  } else if (elapsed < 2600) {
    detail = sampleRunDetailByStatus('RUNNING')
    detail.run_id = runId
    detail.target = currentTarget()
  } else {
    detail = JSON.parse(JSON.stringify(sampleRunDetail)) as RunDetail
    detail.run_id = runId
    detail.target = currentTarget()
  }
  return detail
}

export async function mockGetAnalysis(projectId: string, runId: string, caseId: string): Promise<Analysis> {
  await delay(LATENCY)
  void projectId
  void runId
  const hit = sampleAnalysisMap[caseId]
  if (hit) return hit
  return {
    category: '无法确定',
    reason: '该用例没有可分析的失败证据。',
    evidence: [],
    suggestion: '查看步骤断言差异与错误阶段以定位问题。'
  }
}

/** 从 RunDetail 生成可下载的 HTML 报告（转义后，供浏览器直接打开） */
export function buildHtmlReport(detail: RunDetail): string {
  const esc = (s: string | null | number) =>
    s === null || s === undefined
      ? '<em class="nil">null</em>'
      : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  const rows = detail.results
    .map(
      (r) => `
      <tr>
        <td>${esc(r.title)}</td>
        <td class="outcome-${r.outcome.toLowerCase()}">${esc(r.outcome)}</td>
        <td>${r.steps
          .map(
            (s) => `
            <div class="step">
              <b>${esc(s.name)}</b> (${esc(s.phase)}) — HTTP ${esc(s.http_status)} / ${esc(s.elapsed_ms)}ms
              <div class="diffs">${(s.assertion_diffs ?? []).map((d) => esc(d)).join('<br/>') || '—'}</div>
            </div>`
          )
          .join('')}</td>
      </tr>`
    )
    .join('')

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>TestPilot 运行报告 ${esc(detail.run_id)}</title>
<style>
  body { font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; margin: 32px; color: #1f2329; }
  h1 { font-size: 22px; } h2 { font-size: 16px; margin-top: 24px; }
  table { border-collapse: collapse; width: 100%; margin-top: 12px; }
  th, td { border: 1px solid #e5e6eb; padding: 10px 12px; text-align: left; vertical-align: top; font-size: 13px; }
  th { background: #f7f8fa; }
  .stats span { display: inline-block; margin-right: 16px; font-weight: 600; }
  .outcome-pass { color: #16a34a; font-weight: 700; }
  .outcome-fail { color: #dc2626; font-weight: 700; }
  .outcome-error { color: #ea580c; font-weight: 700; }
  .outcome-blocked { color: #6b7280; font-weight: 700; }
  .step { margin: 6px 0; }
  .diffs { color: #dc2626; margin-top: 4px; }
  .nil { color: #9ca3af; }
</style>
</head>
<body>
  <h1>TestPilot 运行报告</h1>
  <p>批次：<b>${esc(detail.run_id)}</b> · 状态：<b>${esc(detail.status)}</b></p>
  <p>目标：${
    detail.target
      ? `${detail.target.kind === 'local' ? '本地服务' : '演示服务'} <b>${esc(detail.target.service_id)}</b>（${esc(detail.target.base_url)}）${
          detail.target.environment_version == null ? '' : ` · 环境 v${esc(detail.target.environment_version)}`
        }`
      : '<em class="nil">未冻结</em>'
  }</p>
  <p class="stats">
    <span class="outcome-pass">PASS ${detail.counts.PASS}</span>
    <span class="outcome-fail">FAIL ${detail.counts.FAIL}</span>
    <span class="outcome-error">ERROR ${detail.counts.ERROR}</span>
    <span class="outcome-blocked">BLOCKED ${detail.counts.BLOCKED}</span>
  </p>
  <h2>用例结果</h2>
  <table>
    <thead><tr><th>用例</th><th>结果</th><th>步骤</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>
  <p style="margin-top:24px;color:#6b7280;font-size:12px;">报告基于运行快照，摘要已脱敏；不可用字段以 null 表示。</p>
</body>
</html>`
}

export async function mockGetReport(projectId: string, runId: string): Promise<string> {
  await delay(LATENCY)
  void projectId
  const detail = await mockGetRunDetail(projectId, runId)
  return buildHtmlReport(detail)
}

export { DEMO_PROJECT_ID }
