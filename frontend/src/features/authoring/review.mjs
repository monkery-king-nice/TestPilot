export function reviewLabel(review) {
  if (!review || review.source === 'unverified') return '尚未定位到原文，请核对或修改依据'
  const where = review.source === 'document' ? '文档 ' + review.path : '当前需求'
  return (review.exact ? '原文引用 · ' : '相似原句，请核对含义 · ') + where
}

export function inputShape(body) {
  if (body == null) return '无请求体'
  if (Array.isArray(body)) return '数组，共 ' + body.length + ' 项'
  if (typeof body !== 'object') return '单个值'
  return Object.entries(body).map(([key, value]) =>
    Array.isArray(value) ? key + '（' + value.length + ' 项）' : key
  ).join('、') || '空对象'
}

export function assertionLabel(a) {
  if (a.type === 'status') return '预期 HTTP ' + a.expected
  if (a.type === 'elapsed_ms_lte') return '耗时上限 ' + a.expected + ' 毫秒'
  if (a.type === 'nonempty_string') return a.path + ' 应为非空文本'
  if (a.type !== 'json_equals') return '请检查断言类型'
  if (/passw|secret|token|authorization|cookie|api.?key/i.test(a.path)) return a.path + ' 与设定值一致（值已隐藏）'
  // Values in objects and arbitrary text may contain credentials.
  const value = a.expected
  if (value === null || typeof value === 'number' || typeof value === 'boolean') return a.path + ' 应等于 ' + value
  if (Array.isArray(value)) return a.path + ' 应等于指定数组（' + value.length + ' 项）'
  return a.path + ' 应与草稿中的预期值一致'
}
