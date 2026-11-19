<script setup lang="ts">
// 执行页：运行前同屏展示项目、执行目标、需求版本与已确认用例；
// 缺接口/环境/确认时给补充入口，避免直接发起注定失败的批次。
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getEnvironment, listCases, startRun } from '@/api/runs'
import { listEndpoints, listProjects } from '@/api/authoring'
import type { Case, EnvironmentRead, RunTarget } from '@/api/types'
import { describeRequirementVersions, describeTarget, preflightState } from './runContext.mjs'

const route = useRoute()
const router = useRouter()
const projectId = () => String(route.params.projectId)

const loading = ref(false)
const starting = ref(false)
const cases = ref<Case[]>([])
const selected = ref<string[]>([])
const projectName = ref('')
const endpoints = ref<{ id: string }[]>([])
const environment = ref<EnvironmentRead | null>(null)

const confirmed = computed(() => cases.value.filter((c) => c.status === 'CONFIRMED'))
const requirementVersions = computed(() => describeRequirementVersions(confirmed.value))

const environmentTarget = computed<RunTarget | null>(() => {
  const env = environment.value
  if (!env) return null
  return {
    kind: env.target,
    service_id: env.service_id ?? (env.target === 'demo' ? 'demo' : ''),
    base_url: env.base_url ?? '',
    environment_version: env.environment_version
  }
})
const targetLabel = computed(() =>
  environment.value?.environment_version == null ? '未配置' : describeTarget(environmentTarget.value)
)

const preflight = computed(() =>
  preflightState({
    projectId: projectId(),
    confirmedCases: confirmed.value,
    endpoints: endpoints.value,
    environment: environment.value
  })
)

async function load() {
  loading.value = true
  try {
    const [allCases, projects, eps, env] = await Promise.all([
      listCases(projectId()),
      listProjects().catch(() => []),
      listEndpoints(projectId()).catch(() => []),
      getEnvironment(projectId()).catch(() => null)
    ])
    cases.value = allCases
    projectName.value = projects.find((p) => p.id === projectId())?.name ?? projectId()
    endpoints.value = eps
    environment.value = env
    selected.value = confirmed.value.map((c) => c.id)
  } catch (e) {
    ElMessage.error((e as Error).message || '加载执行前信息失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function onRun() {
  if (!preflight.value.ready) {
    ElMessage.warning('运行前信息不完整，请先按提示补充')
    return
  }
  if (!selected.value.length) {
    ElMessage.warning('请至少选择一条已确认用例')
    return
  }
  starting.value = true
  try {
    const payload = confirmed.value
      .filter((c) => selected.value.includes(c.id))
      .map((c) => ({ id: c.id, version: c.version }))
    const res = await startRun(projectId(), {
      cases: payload,
      // 带上页面展示的环境版本：环境在别处被改过时，后端会拒绝创建批次。
      environment_version: environment.value?.environment_version ?? undefined
    })
    ElMessage.success(`运行已发起（${res.status}）`)
    router.push(`/projects/${projectId()}/runs/${res.run_id}`)
  } catch (e) {
    const err = e as { status?: number; message?: string }
    if (err.status === 409) {
      ElMessage.warning(err.message || '项目测试环境已变更，请刷新后重新确认再执行')
      await load() // 重新读取环境与版本，用户确认后再点执行
    } else {
      ElMessage.error(err.message || '发起运行失败')
    }
  } finally {
    starting.value = false
  }
}

function handleSelection(rows: Case[]) {
  selected.value = rows.map((r) => r.id)
}
</script>

<template>
  <div class="page">
    <el-page-header @back="router.back()" title="返回">
      <template #content>
        <span class="ph-title">执行测试</span>
      </template>
    </el-page-header>

    <el-card class="mt16" shadow="never" :body-style="{ padding: '16px 20px' }">
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="项目">{{ projectName }}</el-descriptions-item>
        <el-descriptions-item label="执行目标">{{ targetLabel }}</el-descriptions-item>
        <el-descriptions-item label="需求版本">{{ requirementVersions }}</el-descriptions-item>
        <el-descriptions-item label="已确认用例">{{ confirmed.length }} 条</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-alert
      v-for="item in preflight.missing"
      :key="item.key"
      class="mt12"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #title>
        {{ item.label }} ·
        <router-link :to="item.path">{{ item.hint }}</router-link>
      </template>
    </el-alert>

    <div class="summary mt16">
      <div>
        <div class="summary-label">本次执行</div>
        <div class="summary-value">{{ targetLabel }} · 已选 {{ selected.length }} 条</div>
      </div>
      <el-button type="primary" size="large" :loading="starting" :disabled="!preflight.ready" @click="onRun">
        执行所选（{{ selected.length }}）
      </el-button>
    </div>

    <el-card class="mt16" shadow="never" :body-style="{ padding: '0' }">
      <el-table
        :data="confirmed"
        v-loading="loading"
        @selection-change="handleSelection"
        empty-text="暂无已确认用例"
      >
        <el-table-column type="selection" width="46" />
        <el-table-column label="用例（目标）" min-width="220">
          <template #default="{ row }">
            <div class="case-title">{{ row.title }}</div>
            <div class="basis">{{ row.expected_basis }}</div>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">v{{ row.version }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="需求版本" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="info" effect="plain">v{{ row.requirement_version }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="mt16 hint">
      <el-text type="info" size="small">
        整批 1–20 条、每例 1–5 步；接口/环境/确认不完整时服务端会整批拒绝。仅允许一个运行中批次。
      </el-text>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 940px;
}
.mt16 {
  margin-top: 16px;
}
.mt12 {
  margin-top: 12px;
}
.ph-title {
  font-weight: 600;
}
.summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}
.summary-label {
  font-size: 12px;
  color: #64748b;
}
.summary-value {
  font-size: 15px;
  font-weight: 600;
  margin-top: 4px;
}
.case-title {
  font-weight: 600;
}
.basis {
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
}
.hint {
  text-align: right;
}
</style>
