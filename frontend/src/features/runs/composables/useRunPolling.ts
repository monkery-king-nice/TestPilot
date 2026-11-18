// 运行详情立即查询一次，非终态时继续轮询，离页或切换批次时取消。
import { onUnmounted, ref } from 'vue'
import { getRunDetail } from '@/api/runs'
import type { RunDetail } from '@/api/types'

export function useRunPolling() {
  const detail = ref<RunDetail | null>(null)
  const loading = ref(false)
  const polling = ref(false)
  const error = ref<string | null>(null)
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined

  function stopPolling() {
    controller?.abort()
    clearTimeout(timer)
    polling.value = false
    loading.value = false
  }

  function restore(projectId: string, runId: string) {
    stopPolling()
    const request = new AbortController()
    controller = request
    detail.value = null
    loading.value = true
    error.value = null

    async function tick() {
      try {
        const next = await getRunDetail(projectId, runId, request.signal)
        if (request.signal.aborted) return
        detail.value = next
        polling.value = next.status !== 'COMPLETED' && next.status !== 'INTERRUPTED'
        if (polling.value) timer = setTimeout(tick, 1000)
      } catch (e) {
        if (request.signal.aborted) return
        error.value = (e as Error).message || '拉取运行详情失败'
        polling.value = false
      } finally {
        if (!request.signal.aborted) loading.value = false
      }
    }
    void tick()
  }

  onUnmounted(stopPolling)
  return { detail, loading, polling, error, restore }
}
