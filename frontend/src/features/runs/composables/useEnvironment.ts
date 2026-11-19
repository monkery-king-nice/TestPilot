// 环境配置逻辑：支持演示服务或项目已启动的本地服务；保存后只展示非敏感目标与字段名。
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getEnvironment, putEnvironment } from '@/api/runs'
import type { EnvironmentRead, EnvironmentWrite, TargetKind } from '@/api/types'

export function useEnvironment(projectId: () => string) {
  const target = ref<TargetKind>('demo')
  const serviceId = ref<string | null>(null)
  const baseUrl = ref<string | null>(null)
  const environmentVersion = ref<number | null>(null)
  const configuredKeys = ref<string[]>([])
  const loading = ref(false)
  const saving = ref(false)
  // 读取成功后才允许保存：读取失败时「凭据状态未知」不能当作「没有已保存凭据」。
  const loaded = ref(false)
  const loadError = ref<string | null>(null)

  function apply(env: EnvironmentRead) {
    target.value = env.target
    serviceId.value = env.service_id
    baseUrl.value = env.base_url
    environmentVersion.value = env.environment_version
    configuredKeys.value = env.configured_keys
  }

  async function load() {
    loading.value = true
    loaded.value = false
    loadError.value = null
    try {
      apply(await getEnvironment(projectId()))
      loaded.value = true
    } catch (e) {
      loadError.value = (e as Error).message || '读取环境配置失败'
      ElMessage.error(loadError.value)
    } finally {
      loading.value = false
    }
  }

  async function save(write: EnvironmentWrite) {
    saving.value = true
    try {
      apply(await putEnvironment(projectId(), write))
      ElMessage.success('已保存，仅服务端执行器可读取凭证值')
    } catch (e) {
      ElMessage.error((e as Error).message || '保存失败')
    } finally {
      saving.value = false
    }
  }

  return {
    target,
    serviceId,
    baseUrl,
    environmentVersion,
    configuredKeys,
    loading,
    saving,
    loaded,
    loadError,
    load,
    save
  }
}
