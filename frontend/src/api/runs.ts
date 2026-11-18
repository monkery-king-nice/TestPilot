// 环境、执行与结果相关 API（真实后端）。
// 路由对应 docs/api-alpha.md：P = /api/projects/{project_id}。
// 提供者：曾炜毅(environment)、沈冠宇(cases/report)、周兴宇(runs)、郭泽强(analysis)。

import type {
  Analysis,
  Case,
  EnvironmentRead,
  EnvironmentWrite,
  RunDetail,
  StartRunRequest,
  StartRunResponse
} from './types'
import { apiFetch, projectPath } from './client'
import { USE_MOCK } from './config'
import {
  mockGetAnalysis,
  mockGetCases,
  mockGetEnvironment,
  mockGetReport,
  mockGetRunDetail,
  mockPutEnvironment,
  mockStartRun
} from '@/mocks/mockAdapter'

/** 读取环境：仅返回已配置字段名，不含值 */
export function getEnvironment(projectId: string): Promise<EnvironmentRead> {
  if (USE_MOCK) return mockGetEnvironment(projectId)
  return apiFetch<EnvironmentRead>(projectPath(projectId, '/environment'))
}

/** 写入环境：仅保存字段名供展示，值只给服务端执行器 */
export function putEnvironment(projectId: string, write: EnvironmentWrite): Promise<EnvironmentRead> {
  if (USE_MOCK) return mockPutEnvironment(projectId, write)
  return apiFetch<EnvironmentRead>(projectPath(projectId, '/environment'), {
    method: 'PUT',
    body: JSON.stringify(write)
  })
}

/** 列出用例（前端过滤 CONFIRMED） */
export function listCases(projectId: string): Promise<Case[]> {
  if (USE_MOCK) return mockGetCases(projectId)
  return apiFetch<Case[]>(projectPath(projectId, '/cases'))
}

/** 发起运行（202，返回 QUEUED） */
export function startRun(projectId: string, req: StartRunRequest): Promise<StartRunResponse> {
  if (USE_MOCK) return mockStartRun(projectId, req)
  return apiFetch<StartRunResponse>(projectPath(projectId, '/runs'), {
    method: 'POST',
    body: JSON.stringify(req)
  })
}

/** 查询运行详情（轮询用） */
export function getRunDetail(projectId: string, runId: string): Promise<RunDetail> {
  if (USE_MOCK) return mockGetRunDetail(projectId, runId)
  return apiFetch<RunDetail>(projectPath(projectId, `/runs/${runId}`))
}

/** 失败分析（用户点击触发，仅分析已保存的脱敏结果） */
export function getAnalysis(projectId: string, runId: string, caseId: string): Promise<Analysis> {
  if (USE_MOCK) return mockGetAnalysis(projectId, runId, caseId)
  return apiFetch<Analysis>(projectPath(projectId, `/runs/${runId}/analysis`), {
    method: 'POST',
    body: JSON.stringify({ case_id: caseId })
  })
}

/** 下载 HTML 报告（返回 HTML 文本） */
export function getReportHtml(projectId: string, runId: string): Promise<string> {
  if (USE_MOCK) return mockGetReport(projectId, runId)
  return apiFetch<string>(projectPath(projectId, `/runs/${runId}/report`))
}
