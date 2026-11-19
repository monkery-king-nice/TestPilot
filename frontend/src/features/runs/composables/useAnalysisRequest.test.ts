// 乱序回归测试：分析请求在 A→B 切换与同一用例重试时，迟到响应不能写到错误对象上。
// 运行：cd frontend && node --test src/features/runs/composables/useAnalysisRequest.test.ts
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { useAnalysisRequest, describeAnalysisError } from './useAnalysisRequest.ts'
import type { Analysis } from '@/api/types'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const analysisA: Analysis = { category: 'A', reason: 'A 批次原因', evidence: ['a'], suggestion: 'a' }
const analysisB: Analysis = { category: 'B', reason: 'B 批次原因', evidence: ['b'], suggestion: 'b' }

test('A→B 切换后，A 的迟到响应不会显示在 B 上', async () => {
  const req = useAnalysisRequest()
  req.reset('A||case-1')
  const dA = deferred<Analysis>()
  const pA = req.run('A||case-1', () => dA.promise)

  // 切到 B 批次（同一 case_id，组件会被复用）
  req.reset('B||case-1')
  const dB = deferred<Analysis>()
  const pB = req.run('B||case-1', () => dB.promise)

  dB.resolve(analysisB)
  await pB
  assert.equal(req.analysis.value?.category, 'B')
  assert.equal(req.loading.value, false)

  // A 最后返回：必须被丢弃
  dA.resolve(analysisA)
  await pA
  assert.equal(req.analysis.value?.category, 'B', 'A 的迟到响应不应覆盖 B')
  assert.equal(req.error.value, null)
  assert.equal(req.loading.value, false)
})

test('同一用例重试：旧的迟到响应不覆盖新结果', async () => {
  const req = useAnalysisRequest()
  req.reset('A||case-1')
  const d1 = deferred<Analysis>()
  const p1 = req.run('A||case-1', () => d1.promise)

  const d2 = deferred<Analysis>()
  const p2 = req.run('A||case-1', () => d2.promise)

  d2.resolve({ category: 'retry', reason: '第二次', evidence: [], suggestion: '' })
  await p2
  assert.equal(req.analysis.value?.category, 'retry')

  d1.resolve({ category: 'old', reason: '第一次迟到', evidence: [], suggestion: '' })
  await p1
  assert.equal(req.analysis.value?.category, 'retry')
})

test('接口不可用时给出可读原因，且不写入分析文本', async () => {
  const req = useAnalysisRequest()
  req.reset('A||case-1')
  await req.run('A||case-1', () => Promise.reject(new Error('项目下没有这个运行批次')))
  assert.equal(req.analysis.value, null)
  assert.equal(req.error.value, '项目下没有这个运行批次')
  assert.equal(req.loading.value, false)
})

test('网络错误映射为可读提示', () => {
  assert.equal(describeAnalysisError(new TypeError('Failed to fetch')), '分析服务暂不可用，请稍后重试')
  assert.equal(describeAnalysisError(new Error('模型不可用')), '模型不可用')
})

test('切换批次时的加载态只属于当前请求', async () => {
  const req = useAnalysisRequest()
  req.reset('A||case-1')
  const dA = deferred<Analysis>()
  const pA = req.run('A||case-1', () => dA.promise)
  assert.equal(req.loading.value, true)

  // 切到 B：应清掉 A 的加载态
  req.reset('B||case-1')
  assert.equal(req.loading.value, false)
  assert.equal(req.analysis.value, null)

  dA.resolve(analysisA)
  await pA
  assert.equal(req.loading.value, false, 'A 的 finally 不应影响已切换的 B')
  assert.equal(req.analysis.value, null)
})
