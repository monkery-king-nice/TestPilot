// 失败分析请求的状态与乱序保护。
// 详情页在 A→B 批次之间会复用组件（同一 case_id），若直接把响应写进分析文本，
// A 的迟到响应会显示在 B 上。这里用「请求序号 + 请求键（项目/批次/用例）」双重校验：
// 只有仍属于当前对象、且是最新一次请求的响应，才允许写入。
import { ref, type Ref } from 'vue'
import type { Analysis } from '@/api/types'

export interface AnalysisRequestHandle {
  analysis: Ref<Analysis | null>
  loading: Ref<boolean>
  error: Ref<string | null>
  /** 切换到新的对象（批次/用例）时调用：清空状态并作废在途请求。 */
  reset(key: string): void
  /** 发起请求；fetcher 由调用方提供，便于测试注入可控返回顺序的替身。 */
  run(key: string, fetcher: () => Promise<Analysis>): Promise<void>
}

export function useAnalysisRequest(): AnalysisRequestHandle {
  const analysis: Ref<Analysis | null> = ref(null)
  const loading = ref(false)
  const error: Ref<string | null> = ref(null)
  let seq = 0
  let currentKey: string | null = null

  function reset(key: string) {
    seq++
    currentKey = key
    loading.value = false
    analysis.value = null
    error.value = null
  }

  async function run(key: string, fetcher: () => Promise<Analysis>) {
    const mySeq = ++seq
    currentKey = key
    loading.value = true
    error.value = null
    try {
      const result = await fetcher()
      // 已切换批次/用例（或又发起了新请求）：丢弃迟到响应。
      if (mySeq !== seq || key !== currentKey) return
      analysis.value = result
    } catch (e) {
      if (mySeq !== seq || key !== currentKey) return
      error.value = describeAnalysisError(e)
    } finally {
      // 只有仍是当前请求时才结束 loading，避免把新请求的加载态清掉。
      if (mySeq === seq && key === currentKey) loading.value = false
    }
  }

  return { analysis, loading, error, reset, run }
}

/** 把接口/网络错误转成可读原因。 */
export function describeAnalysisError(e: unknown): string {
  if (e instanceof Error && e.message && !/failed to fetch|network ?error|load failed/i.test(e.message)) {
    return e.message
  }
  return '分析服务暂不可用，请稍后重试'
}
