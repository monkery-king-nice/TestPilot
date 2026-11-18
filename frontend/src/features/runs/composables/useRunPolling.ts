// 运行轮询逻辑：发起运行 → 按 run_id 轮询 → 终态停止；刷新后从后端恢复。
import { onUnmounted, ref } from 'vue'
import { getRunDetail } from '@/api/runs'
import type { RunDetail, RunStatus } from '@/api/types'

const TERMINAL: RunStatus[] = ['COMPLETED', 'INTERRUPTED']
const POLL_INTERVAL_MS = 1000

export function useRunPolling() {
  const detail = ref<RunDetail | null>(null)
  const loading = ref(false)
  const polling = ref(false)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null

  function isTerminal(status: RunStatus): boolean {
    return TERMINAL.includes(status)
  }

  function stopPolling() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    polling.value = false
  }

  async function fetchOnce(projectId: string, runId: string): Promise<RunDetail> {
    const d = await getRunDetail(projectId, runId)
    detail.value = d
    return d
  }

  /** 轮询直到终态；每次先拉取再决定是否继续。 */
  async function poll(projectId: string, runId: string) {
    stopPolling()
    polling.value = true
    error.value = null

    const tick = async () => {
      try {
        const d = await fetchOnce(projectId, runId)
        if (isTerminal(d.status)) {
          stopPolling()
          return
        }
      } catch (e) {
        error.value = (e as Error).message || '拉取运行详情失败'
        stopPolling()
        return
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS)
    }
    await tick()
  }

  /** 刷新恢复：立即拉取一次，非终态则继续轮询。 */
  async function restore(projectId: string, runId: string) {
    loading.value = true
    error.value = null
    try {
      const d = await fetchOnce(projectId, runId)
      if (isTerminal(d.status)) {
        stopPolling()
      } else {
        await poll(projectId, runId)
      }
    } catch (e) {
      error.value = (e as Error).message || '恢复运行详情失败'
      stopPolling()
    } finally {
      loading.value = false
    }
  }

  onUnmounted(stopPolling)

  return { detail, loading, polling, error, poll, restore, stopPolling, isTerminal }
}
