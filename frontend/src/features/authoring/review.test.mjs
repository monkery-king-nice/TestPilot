import test from 'node:test'
import assert from 'node:assert/strict'
import { inputShape, assertionLabel, reviewLabel } from './review.mjs'

test('摘要按实际输入呈现，隐藏请求正文及敏感字段预期', () => {
  assert.equal(inputShape({ units: [1, 2, 3], password: 'private-fixture' }), 'units（3 项）、password')
  assert.equal(inputShape(null), '无请求体')
  assert.doesNotMatch(assertionLabel({type:'json_equals', path:'access_token', expected:'private-fixture'}), /private-fixture/)
  assert.match(assertionLabel({type:'json_equals', path:'available', expected:false}), /false/)
})

test('原句、相似依据、未定位和旧候选均有复核提示', () => {
  assert.match(reviewLabel({source:'requirement', exact:true}), /原文引用/)
  assert.match(reviewLabel({source:'document', exact:false, path:'rules.md'}), /相似原句.*rules.md/)
  assert.match(reviewLabel({source:'unverified'}), /请核对/)
  assert.match(reviewLabel(undefined), /请核对/)
})
