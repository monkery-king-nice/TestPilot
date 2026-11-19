// 执行页/结果页纯逻辑回归测试（Node 18+ 可直接运行）。
// 运行：cd frontend && node --test src/features/runs/runContext.test.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  describeTarget,
  describeRequirementVersions,
  isEnvironmentConfigured,
  preflightState
} from './runContext.mjs'

const demoTarget = { kind: 'demo', service_id: 'demo', base_url: 'http://127.0.0.1:8010', environment_version: 1 }
const localTarget = { kind: 'local', service_id: '项目A', base_url: 'http://127.0.0.1:8080', environment_version: 3 }
const localEnv = { target: 'local', service_id: '项目A', base_url: 'http://127.0.0.1:8080', environment_version: 3, configured_keys: ['password', 'username'] }

test('目标文案区分演示服务与本地服务，并带环境版本', () => {
  assert.match(describeTarget(demoTarget), /演示服务 demo/)
  assert.match(describeTarget(localTarget), /本地服务 项目A（http:\/\/127\.0\.0\.1:8080） · 环境 v3/)
  assert.equal(describeTarget(null), '未冻结目标（旧批次）')
})

test('需求版本汇总去重', () => {
  const cases = [{ requirement_version: 2 }, { requirement_version: 2 }, { requirement_version: 3 }]
  assert.equal(describeRequirementVersions(cases), 'v2、v3')
  assert.equal(describeRequirementVersions([]), '—')
})

test('环境是否已配置', () => {
  assert.equal(isEnvironmentConfigured(localEnv), true)
  assert.equal(isEnvironmentConfigured({ ...localEnv, configured_keys: [], environment_version: null }), false)
  assert.equal(isEnvironmentConfigured(null), false)
})

test('运行前检查：三项齐全才 ready', () => {
  const state = preflightState({
    projectId: 'p1',
    confirmedCases: [{ id: 'c1', requirement_version: 1 }],
    endpoints: [{ id: 'e1' }],
    environment: localEnv
  })
  assert.equal(state.ready, true)
  assert.deepEqual(state.missing, [])
})

test('运行前检查：缺少接口/环境/确认用例时给出补充入口', () => {
  const state = preflightState({
    projectId: 'p1',
    confirmedCases: [],
    endpoints: [],
    environment: { target: 'demo', service_id: null, base_url: null, environment_version: null, configured_keys: [] }
  })
  assert.equal(state.ready, false)
  assert.deepEqual(
    state.missing.map((m) => m.key),
    ['endpoints', 'environment', 'cases']
  )
  assert.equal(state.missing[0].path, '/projects/p1/requirements')
  assert.equal(state.missing[1].path, '/projects/p1/environment')
  assert.equal(state.missing[2].path, '/projects/p1/cases')
})

test('只缺环境时也能定位到环境页', () => {
  const state = preflightState({
    projectId: 'p2',
    confirmedCases: [{ id: 'c1', requirement_version: 1 }],
    endpoints: [{ id: 'e1' }],
    environment: null
  })
  assert.equal(state.ready, false)
  assert.deepEqual(state.missing.map((m) => m.key), ['environment'])
  assert.equal(state.missing[0].path, '/projects/p2/environment')
})
