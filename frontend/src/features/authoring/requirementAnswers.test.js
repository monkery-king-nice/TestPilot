import assert from 'node:assert/strict'
import { test } from 'node:test'
import { composeSupplement } from './requirementAnswers.ts'

test('补充保留原文、引用和来源，跳过空答案并检查长度', () => {
  const questions = [{ quote: '按名称查询', question: '为空时返回什么？', source_path: 'docs/rules.md' },
    { quote: '返回记录', question: '最多多少条？' }]
  const combined = composeSupplement('原文\r\n', 1, questions, ['  返回 422\n并说明原因  ', ' '])
  assert.ok(combined.startsWith('原文\r\n\n\n'))
  assert.ok(combined.includes('基于需求 v1'))
  assert.ok(combined.includes('来源：docs/rules.md'))
  assert.ok(combined.includes('回答：返回 422\n并说明原因'))
  assert.ok(!combined.includes('最多多少条'))
  assert.throws(() => composeSupplement('正文', 1, questions, []), /至少/)
  assert.throws(() => composeSupplement('中'.repeat(16000), 1, questions, ['答案']), /16000/)
})
