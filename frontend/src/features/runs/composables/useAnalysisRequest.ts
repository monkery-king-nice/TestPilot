// 失败分析请求的 Vue 包装：把纯 JS 状态模块（analysisRequestStore.mjs）映射为响应式 ref。
// 纯 JS 模块可在 Node 18+ 直接测试，避免测试命令依赖 Node 22 的 TypeScript 支持。
import { ref, type Ref } from 'vue'
import type { Analysis } from '@/api/types'
import { createAnalysisRequestStore, describeAnalysisError } from './analysisRequestStore.mjs'

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
  const store = createAnalysisRequestStore()
  const analysis: Ref<Analysis | null> = ref(null)
  const loading = ref(false)
  const error: Ref<string | null> = ref(null)

  function sync() {
    analysis.value = store.analysis
    loading.value = store.loading
    error.value = store.error
  }

  function reset(key: string) {
    store.reset(key)
    sync()
  }

  async function run(key: string, fetcher: () => Promise<Analysis>) {
    const pending = store.run(key, fetcher)
    sync() // 立刻反映 loading / 清掉旧分析
    await pending
    sync()
  }

  return { analysis, loading, error, reset, run }
}

export { describeAnalysisError }
