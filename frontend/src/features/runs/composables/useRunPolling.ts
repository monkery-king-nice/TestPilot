// 运行轮询逻辑：发起运行 → 按 run_id 轮询 → 终态停止；刷新后从后端恢复。
// 离开详情页（组件卸载）会立即停止轮询；地址中的批次变化时重新加载。
// generation 令牌与批次 ID 双重校验：晚到的响应只有在「仍属于当前轮询、且批次一致」时才更新页面，
// 否则丢弃，避免旧批次覆盖新批次。
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
  // 每次开始/停止轮询都自增。晚到的响应发现令牌不一致就丢弃，不再启动下一次查询。
  let generation = 0

  function isTerminal(status: RunStatus): boolean {
    return TERMINAL.includes(status)
  }

  function stopPolling() {
    generation++
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
    polling.value = false
  }

  /** 仅拉取，不改页面状态；由调用方在确认批次与令牌后写入 detail。 */
  async function fetchRun(projectId: string, runId: string): Promise<RunDetail> {
    return await getRunDetail(projectId, runId)
  }

  /** 轮询直到终态；每次先拉取再决定是否继续。 */
  async function poll(projectId: string, runId: string) {
    stopPolling()
    const token = generation
    polling.value = true
    error.value = null

    const tick = async () => {
      if (token !== generation) return
      try {
        const d = await fetchRun(projectId, runId)
        // 组件已卸载 / 已切换到别的批次 / 响应不属于当前批次：丢弃，不再排下一次。
        if (token !== generation || d.run_id !== runId) return
        detail.value = d
        if (isTerminal(d.status)) {
          stopPolling()
          return
        }
      } catch (e) {
        if (token !== generation) return
        error.value = (e as Error).message || '拉取运行详情失败'
        stopPolling()
        return
      }
      timer = setTimeout(tick, POLL_INTERVAL_MS)
    }
    await tick()
  }

  /** 刷新/切换批次：立即拉取一次，非终态则继续轮询。 */
  async function restore(projectId: string, runId: string) {
    stopPolling()
    const token = generation
    loading.value = true
    error.value = null
    try {
      const d = await fetchRun(projectId, runId)
      if (token !== generation || d.run_id !== runId) return
      detail.value = d
      if (isTerminal(d.status)) {
        stopPolling()
      } else {
        await poll(projectId, runId)
      }
    } catch (e) {
      if (token !== generation) return
      error.value = (e as Error).message || '恢复运行详情失败'
      stopPolling()
    } finally {
      loading.value = false
    }
  }

  onUnmounted(() => {
    stopPolling()
  })

  return { detail, loading, polling, error, poll, restore, stopPolling, isTerminal }
}
