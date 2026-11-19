// TestPilot Alpha v1 共享类型定义
// 依据：docs/api-alpha.md（六人共同接口约定）
// 提供者对应关系：
//   曾炜毅 - environment；沈冠宇 - cases/report；周兴宇 - runs(RunDetail)；郭泽强 - analysis

/** 用例状态 */
export type CaseStatus = 'DRAFT' | 'NEEDS_INFO' | 'READY' | 'CONFIRMED' | 'NEEDS_REVIEW'

/** 步骤阶段 */
export type StepPhase = 'setup' | 'test' | 'teardown'

/** 断言类型 */
export type AssertionType = 'status' | 'nonempty_string' | 'json_equals' | 'elapsed_ms_lte'

/** 批次状态 */
export type RunStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'INTERRUPTED'

/** 用例结果 */
export type Outcome = 'PASS' | 'FAIL' | 'ERROR' | 'BLOCKED'

export interface Assertion {
  type: AssertionType
  /** status 断言的期望状态码 */
  expected?: unknown
  /** json 断言的字段路径（点分隔） */
  path?: string | null
}

/** CaseDraft 中的一步（见共同接口约定） */
export interface CaseStep {
  name: string
  phase: StepPhase
  endpoint_id: string
  endpoint_version: number
  headers: Record<string, string>
  body: unknown
  assertions: Assertion[]
  extract: Record<string, string>
}

/** 已保存的用例（含 id/version/status） */
export interface CaseDraft {
  title: string
  requirement_id: string
  requirement_version: number
  expected_basis: string
  steps: CaseStep[]
}

export interface Case extends CaseDraft {
  id: string
  version: number
  status: CaseStatus
  reasons?: string[]
}

/** 执行目标类型：demo 为团队演示服务，local 为项目已启动的本地服务 */
export type TargetKind = 'demo' | 'local'

/** 环境读取结果：只返回非敏感目标与字段名（值仅服务端执行器可读） */
export interface EnvironmentRead {
  target: TargetKind
  service_id: string | null
  base_url: string | null
  environment_version: number | null
  configured_keys: string[]
}

/** 环境写入请求：demo 必须带 secrets；local 可省略（无登录的本地服务） */
export interface EnvironmentWrite {
  target: TargetKind
  service_id?: string | null
  base_url?: string | null
  secrets?: { username: string; password: string }
}

/** 运行批次冻结的执行目标（新批次在创建时冻结） */
export interface RunTarget {
  kind: TargetKind
  service_id: string
  base_url: string
  environment_version: number | null
}

/** 发起运行请求 */
export interface StartRunRequest {
  cases: Array<{ id: string; version: number }>
  /** 页面展示的环境版本；后端据此校验，环境已变更时拒绝创建批次 */
  environment_version?: number
}

/** 发起运行响应（202） */
export interface StartRunResponse {
  run_id: string
  status: 'QUEUED'
}

/** 单步执行结果 */
export interface RunStepResult {
  name: string
  phase: StepPhase
  http_status: number | null
  elapsed_ms: number | null
  request_summary: string | null
  response_summary: string | null
  assertion_diffs: string[]
  error_stage: string | null
}

/** 单条用例执行结果 */
export interface RunResult {
  case_id: string
  title: string
  outcome: Outcome
  steps: RunStepResult[]
}

/** RunDetail（周兴宇提供） */
export interface RunDetail {
  run_id: string
  status: RunStatus
  /** 创建批次时冻结的目标；旧批次可能为 null（沿用 demo 行为） */
  target: RunTarget | null
  counts: {
    PASS: number
    FAIL: number
    ERROR: number
    BLOCKED: number
  }
  results: RunResult[]
}

/** 失败分析结果（郭泽强提供，仅分析已保存的脱敏结果） */
export interface Analysis {
  category: string
  reason: string
  evidence: string[]
  suggestion: string
}

/** 统一错误格式 */
export interface ApiError {
  detail: string
}
