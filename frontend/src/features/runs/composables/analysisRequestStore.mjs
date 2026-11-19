// 失败分析请求的状态与乱序保护（纯 JS，无框架依赖，可在 Node 18+ 直接用 node --test 运行）。
// 组件在批次/用例之间会复用：用「请求序号 + 项目/批次/用例」双重校验，
// 晚到响应只有在仍属于当前对象时才写入；重试时先清掉旧分析，避免“错误 + 旧结果”并存。
export function describeAnalysisError(e) {
  if (e instanceof Error && e.message && !/failed to fetch|network ?error|load failed/i.test(e.message)) {
    return e.message
  }
  return '分析服务暂不可用，请稍后重试'
}

export function createAnalysisRequestStore() {
  let analysis = null
  let loading = false
  let error = null
  let seq = 0
  let currentKey = null

  function reset(key) {
    seq++
    currentKey = key
    loading = false
    analysis = null
    error = null
  }

  async function run(key, fetcher) {
    const mySeq = ++seq
    currentKey = key
    loading = true
    error = null
    // 重试时清掉上一次的分析，避免失败时同时显示错误与旧结果。
    analysis = null
    try {
      const result = await fetcher()
      // 已切换批次/用例（或又发起了新请求）：丢弃迟到响应。
      if (mySeq !== seq || key !== currentKey) return
      analysis = result
    } catch (e) {
      if (mySeq !== seq || key !== currentKey) return
      error = describeAnalysisError(e)
    } finally {
      // 只有仍是当前请求时才结束 loading，避免把新请求的加载态清掉。
      if (mySeq === seq && key === currentKey) loading = false
    }
  }

  return {
    get analysis() {
      return analysis
    },
    get loading() {
      return loading
    },
    get error() {
      return error
    },
    reset,
    run
  }
}
