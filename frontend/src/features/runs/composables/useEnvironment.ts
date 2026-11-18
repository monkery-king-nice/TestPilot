// 环境配置逻辑：保存后仅展示已配置字段名（值不返回前端）。
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getEnvironment, putEnvironment } from '@/api/runs'
import type { EnvironmentRead } from '@/api/types'

export function useEnvironment(projectId: () => string) {
  const target = ref<'demo'>('demo')
  const configuredKeys = ref<string[]>([])
  const loading = ref(false)
  const saving = ref(false)

  async function load() {
    loading.value = true
    try {
      const env = await getEnvironment(projectId())
      target.value = env.target
      configuredKeys.value = env.configured_keys
    } catch (e) {
      ElMessage.error((e as Error).message || '读取环境配置失败')
    } finally {
      loading.value = false
    }
  }

  async function save(secrets: Record<string, string>) {
    saving.value = true
    try {
      const env: EnvironmentRead = await putEnvironment(projectId(), {
        target: 'demo',
        secrets
      })
      target.value = env.target
      configuredKeys.value = env.configured_keys
      ElMessage.success('已保存，仅服务端执行器可读取凭证值')
    } catch (e) {
      ElMessage.error((e as Error).message || '保存失败')
    } finally {
      saving.value = false
    }
  }

  return { target, configuredKeys, loading, saving, load, save }
}
