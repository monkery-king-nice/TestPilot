// 四类状态的 RunDetail 示例（同一份示例贯穿联调与演示）。
// 依据共同接口约定：counts 四键初始均为 0，终态四类之和等于所选用例数；
// summary 为脱敏字符串、diffs 为字符串数组，不可用标量用 null。
// 样例中的 req-1、ep-login、ep-me 在实际联调中需替换为真实 ID。

import type { Case, RunDetail } from '@/api/types'

/** 已确认用例列表（运行前展示，含版本） */
export const sampleConfirmedCases: Case[] = [
  {
    id: 'case-login-me',
    title: '登录后获取本人信息',
    version: 2,
    status: 'CONFIRMED',
    requirement_id: 'req-1',
    requirement_version: 2,
    expected_basis: '已确认需求：返回本人编号 demo-user',
    steps: [
      {
        name: 'login',
        phase: 'setup',
        endpoint_id: 'ep-login',
        endpoint_version: 1,
        headers: {},
        body: { username: '{{env.username}}', password: '{{env.password}}' },
        assertions: [
          { type: 'status', expected: 200 },
          { type: 'nonempty_string', path: 'token' }
        ],
        extract: { token: 'token' }
      },
      {
        name: 'me',
        phase: 'test',
        endpoint_id: 'ep-me',
        endpoint_version: 1,
        headers: { Authorization: 'Bearer {{steps.login.token}}' },
        body: null,
        assertions: [
          { type: 'status', expected: 200 },
          { type: 'json_equals', path: 'user.id', expected: 'demo-user' },
          { type: 'elapsed_ms_lte', expected: 3000 }
        ],
        extract: {}
      }
    ]
  },
  {
    id: 'case-wrong-password',
    title: '错误密码应返回 401',
    version: 1,
    status: 'CONFIRMED',
    requirement_id: 'req-1',
    requirement_version: 2,
    expected_basis: '已确认需求：错误密码返回 401 和 code=INVALID_CREDENTIALS',
    steps: [
      {
        name: 'login',
        phase: 'test',
        endpoint_id: 'ep-login',
        endpoint_version: 1,
        headers: {},
        body: { username: '{{env.username}}', password: '{{env.password}}' },
        assertions: [
          { type: 'status', expected: 401 },
          { type: 'json_equals', path: 'code', expected: 'INVALID_CREDENTIALS' }
        ],
        extract: {}
      }
    ]
  },
  {
    id: 'case-user-id-mismatch',
    title: '登录后用户编号应为 demo-user',
    version: 1,
    status: 'CONFIRMED',
    requirement_id: 'req-1',
    requirement_version: 2,
    expected_basis: '已确认需求：/me 返回 user.id=demo-user',
    steps: [
      {
        name: 'login',
        phase: 'setup',
        endpoint_id: 'ep-login',
        endpoint_version: 1,
        headers: {},
        body: { username: '{{env.username}}', password: '{{env.password}}' },
        assertions: [{ type: 'status', expected: 200 }],
        extract: { token: 'token' }
      },
      {
        name: 'me',
        phase: 'test',
        endpoint_id: 'ep-me',
        endpoint_version: 1,
        headers: { Authorization: 'Bearer {{steps.login.token}}' },
        body: null,
        assertions: [{ type: 'json_equals', path: 'user.id', expected: 'demo-user' }],
        extract: {}
      }
    ]
  },
  {
    id: 'case-me-timeout',
    title: '/me 响应耗时不超过 3000ms',
    version: 1,
    status: 'CONFIRMED',
    requirement_id: 'req-1',
    requirement_version: 2,
    expected_basis: '已确认需求：GET /me 耗时上限 3000ms',
    steps: [
      {
        name: 'login',
        phase: 'setup',
        endpoint_id: 'ep-login',
        endpoint_version: 1,
        headers: {},
        body: { username: '{{env.username}}', password: '{{env.password}}' },
        assertions: [{ type: 'status', expected: 200 }],
        extract: { token: 'token' }
      },
      {
        name: 'me',
        phase: 'test',
        endpoint_id: 'ep-me',
        endpoint_version: 1,
        headers: { Authorization: 'Bearer {{steps.login.token}}' },
        body: null,
        assertions: [{ type: 'elapsed_ms_lte', expected: 3000 }],
        extract: {}
      }
    ]
  },
  {
    id: 'case-no-token',
    title: '未配置凭证时登录被阻断',
    version: 1,
    status: 'CONFIRMED',
    requirement_id: 'req-1',
    requirement_version: 2,
    expected_basis: '已确认需求：准备阶段未拿到 token 时主步骤标记 BLOCKED',
    steps: [
      {
        name: 'login',
        phase: 'setup',
        endpoint_id: 'ep-login',
        endpoint_version: 1,
        headers: {},
        body: { username: '{{env.username}}', password: '{{env.password}}' },
        assertions: [
          { type: 'status', expected: 200 },
          { type: 'nonempty_string', path: 'token' }
        ],
        extract: { token: 'token' }
      },
      {
        name: 'me',
        phase: 'test',
        endpoint_id: 'ep-me',
        endpoint_version: 1,
        headers: { Authorization: 'Bearer {{steps.login.token}}' },
        body: null,
        assertions: [{ type: 'status', expected: 200 }],
        extract: {}
      }
    ]
  }
]

/** 四类状态的结果示例（终态 COMPLETED，counts 之和等于 results 数量） */
export const sampleRunDetail: RunDetail = {
  run_id: 'run-demo-0001',
  status: 'COMPLETED',
  counts: { PASS: 2, FAIL: 1, ERROR: 1, BLOCKED: 1 },
  results: [
    // PASS：成功登录 → 查本人信息
    {
      case_id: 'case-login-me',
      title: '登录后获取本人信息',
      outcome: 'PASS',
      steps: [
        {
          name: 'login',
          phase: 'setup',
          http_status: 200,
          elapsed_ms: 84,
          request_summary: 'POST /auth/login body={username:"demo",password:"***"}',
          response_summary: '200 {token:"***",user:{id:"demo-user"}}',
          assertion_diffs: [],
          error_stage: null
        },
        {
          name: 'me',
          phase: 'test',
          http_status: 200,
          elapsed_ms: 132,
          request_summary: 'GET /me headers={Authorization:"Bearer ***"}',
          response_summary: '200 {user:{id:"demo-user"}}',
          assertion_diffs: [],
          error_stage: null
        }
      ]
    },
    // PASS：错误密码且预期 401 判 PASS
    {
      case_id: 'case-wrong-password',
      title: '错误密码应返回 401',
      outcome: 'PASS',
      steps: [
        {
          name: 'login',
          phase: 'test',
          http_status: 401,
          elapsed_ms: 61,
          request_summary: 'POST /auth/login body={username:"demo",password:"***"}',
          response_summary: '401 {code:"INVALID_CREDENTIALS"}',
          assertion_diffs: [],
          error_stage: null
        }
      ]
    },
    // FAIL：真实值偏离已确认预期（user.id 不符）
    {
      case_id: 'case-user-id-mismatch',
      title: '登录后用户编号应为 demo-user',
      outcome: 'FAIL',
      steps: [
        {
          name: 'login',
          phase: 'setup',
          http_status: 200,
          elapsed_ms: 78,
          request_summary: 'POST /auth/login body={username:"demo",password:"***"}',
          response_summary: '200 {token:"***"}',
          assertion_diffs: [],
          error_stage: null
        },
        {
          name: 'me',
          phase: 'test',
          http_status: 200,
          elapsed_ms: 117,
          request_summary: 'GET /me headers={Authorization:"Bearer ***"}',
          response_summary: '200 {user:{id:"demo-user-2"}}',
          assertion_diffs: ['json_equals user.id 期望 "demo-user"，实际 "demo-user-2"'],
          error_stage: null
        }
      ]
    },
    // ERROR：超时（超过 3000ms）
    {
      case_id: 'case-me-timeout',
      title: '/me 响应耗时不超过 3000ms',
      outcome: 'ERROR',
      steps: [
        {
          name: 'login',
          phase: 'setup',
          http_status: 200,
          elapsed_ms: 71,
          request_summary: 'POST /auth/login body={username:"demo",password:"***"}',
          response_summary: '200 {token:"***"}',
          assertion_diffs: [],
          error_stage: null
        },
        {
          name: 'me',
          phase: 'test',
          http_status: null,
          elapsed_ms: 3210,
          request_summary: 'GET /me headers={Authorization:"Bearer ***"}',
          response_summary: null,
          assertion_diffs: [],
          error_stage: 'request timeout (limit 3000ms)'
        }
      ]
    },
    // BLOCKED：准备阶段未拿到 token
    {
      case_id: 'case-no-token',
      title: '未配置凭证时登录被阻断',
      outcome: 'BLOCKED',
      steps: [
        {
          name: 'login',
          phase: 'setup',
          http_status: null,
          elapsed_ms: null,
          request_summary: 'POST /auth/login body={username:"{{env.username}}",password:"{{env.password}}"}',
          response_summary: null,
          assertion_diffs: ['环境变量 env.username / env.password 未配置'],
          error_stage: 'setup'
        },
        {
          name: 'me',
          phase: 'test',
          http_status: null,
          elapsed_ms: null,
          request_summary: null,
          response_summary: null,
          assertion_diffs: ['前置步骤 login 未通过，本步骤未执行'],
          error_stage: 'setup'
        }
      ]
    }
  ]
}

/** 失败分析示例（对 FAIL 用例） */
export const sampleAnalysisMap: Record<string, { category: string; reason: string; evidence: string[]; suggestion: string }> = {
  'case-user-id-mismatch': {
    category: '业务断言失败',
    reason: 'GET /me 实际返回 user.id=demo-user-2，与已确认预期 demo-user 不一致。',
    evidence: ['response_summary: 200 {user:{id:"demo-user-2"}}', 'assertion: json_equals user.id 期望 demo-user'],
    suggestion: '核对演示服务 /me 的实现，或重新确认需求中用户编号的取值。'
  },
  'case-me-timeout': {
    category: '超时',
    reason: 'GET /me 耗时 3210ms，超过 3000ms 上限，判定为执行错误。',
    evidence: ['elapsed_ms=3210', 'error_stage=request timeout (limit 3000ms)'],
    suggestion: '检查演示服务性能或放宽耗时上限（需与需求方确认）。'
  },
  'case-no-token': {
    category: '准备失败',
    reason: '环境未配置 username/password，login 步骤无法解析变量，主步骤被阻断。',
    evidence: ['assertion_diffs: 环境变量 env.username / env.password 未配置', 'error_stage=setup'],
    suggestion: '先在环境页配置演示凭证，再重新发起运行。'
  }
}

/** 运行中的过渡状态（用于演示轮询：QUEUED → RUNNING → COMPLETED） */
export function sampleRunDetailByStatus(status: 'RUNNING' | 'COMPLETED'): RunDetail {
  const detail: RunDetail = JSON.parse(JSON.stringify(sampleRunDetail)) as RunDetail
  detail.status = status
  if (status === 'RUNNING') {
    // 运行中：只展示已结束的部分结果
    detail.counts = { PASS: 1, FAIL: 0, ERROR: 0, BLOCKED: 0 }
    detail.results = sampleRunDetail.results.slice(0, 1)
  }
  return detail
}
