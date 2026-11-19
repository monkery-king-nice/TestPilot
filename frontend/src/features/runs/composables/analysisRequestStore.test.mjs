// 乱序回归测试（纯 JS，Node 18+ 可直接运行）：
// A→B 切换、同一用例重试、首次成功→重试失败、加载/错误/文本三类状态。
// 运行：cd frontend && node --test src/features/runs/composables/analysisRequestStore.test.mjs
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createAnalysisRequestStore, describeAnalysisError } from './analysisRequestStore.mjs'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const A = { category: 'A', reason: 'A 批次原因', evidence: ['a'], suggestion: 'a' }
const B = { category: 'B', reason: 'B 批次原因', evidence: ['b'], suggestion: 'b' }

test('A→B 切换后，A 的迟到响应不会显示在 B 上', async () => {
  const store = createAnalysisRequestStore()
  store.reset('A||case-1')
  const dA = deferred()
  const pA = store.run('A||case-1', () => dA.promise)

  // 切到 B 批次（同一 case_id，组件会被复用）
  store.reset('B||case-1')
  const dB = deferred()
  const pB = store.run('B||case-1', () => dB.promise)

  dB.resolve(B)
  await pB
  assert.equal(store.analysis?.category, 'B')
  assert.equal(store.loading, false)

  // A 最后返回：必须被丢弃
  dA.resolve(A)
  await pA
  assert.equal(store.analysis?.category, 'B', 'A 的迟到响应不应覆盖 B')
  assert.equal(store.error, null)
  assert.equal(store.loading, false)
})

test('同一用例重试：旧的迟到响应不覆盖新结果', async () => {
  const store = createAnalysisRequestStore()
  store.reset('A||case-1')
  const d1 = deferred()
  const p1 = store.run('A||case-1', () => d1.promise)

  const d2 = deferred()
  const p2 = store.run('A||case-1', () => d2.promise)

  d2.resolve({ category: 'retry', reason: '第二次', evidence: [], suggestion: '' })
  await p2
  assert.equal(store.analysis?.category, 'retry')

  d1.resolve({ category: 'old', reason: '第一次迟到', evidence: [], suggestion: '' })
  await p1
  assert.equal(store.analysis?.category, 'retry')
})

test('首次成功 → 重试失败：清掉旧分析，只显示错误', async () => {
  const store = createAnalysisRequestStore()
  store.reset('A||case-1')
  await store.run('A||case-1', () =>
    Promise.resolve({ category: 'ok', reason: '成功', evidence: [], suggestion: '' })
  )
  assert.equal(store.analysis?.category, 'ok')

  // 同一用例重试，接口返回 502
  await store.run('A||case-1', () => Promise.reject(new Error('分析服务返回 502')))
  assert.equal(store.analysis, null, '重试失败时不应保留上一次分析')
  assert.equal(store.error, '分析服务返回 502')
  assert.equal(store.loading, false)
})

test('接口不可用时给出可读原因，且不写入分析文本', async () => {
  const store = createAnalysisRequestStore()
  store.reset('A||case-1')
  await store.run('A||case-1', () => Promise.reject(new Error('项目下没有这个运行批次')))
  assert.equal(store.analysis, null)
  assert.equal(store.error, '项目下没有这个运行批次')
  assert.equal(store.loading, false)
})

test('网络错误映射为可读提示', () => {
  assert.equal(describeAnalysisError(new TypeError('Failed to fetch')), '分析服务暂不可用，请稍后重试')
  assert.equal(describeAnalysisError(new Error('模型不可用')), '模型不可用')
})

test('切换批次时的加载态只属于当前请求', async () => {
  const store = createAnalysisRequestStore()
  store.reset('A||case-1')
  const dA = deferred()
  const pA = store.run('A||case-1', () => dA.promise)
  assert.equal(store.loading, true)

  // 切到 B：应清掉 A 的加载态
  store.reset('B||case-1')
  assert.equal(store.loading, false)
  assert.equal(store.analysis, null)

  dA.resolve(A)
  await pA
  assert.equal(store.loading, false, 'A 的 finally 不应影响已切换的 B')
  assert.equal(store.analysis, null)
})
