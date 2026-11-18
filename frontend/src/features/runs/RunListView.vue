<script setup lang="ts">
// 执行页：列出已确认用例和版本，展示目标、条数与执行按钮；发起运行后跳转详情页。
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listCases, startRun } from '@/api/runs'
import type { Case } from '@/api/types'

const route = useRoute()
const router = useRouter()
const projectId = () => String(route.params.projectId)

const loading = ref(false)
const starting = ref(false)
const cases = ref<Case[]>([])
const selected = ref<string[]>([])

const confirmed = computed(() => cases.value.filter((c) => c.status === 'CONFIRMED'))

async function load() {
  loading.value = true
  try {
    const all = await listCases(projectId())
    cases.value = all
    selected.value = confirmed.value.map((c) => c.id)
  } catch (e) {
    ElMessage.error((e as Error).message || '加载用例失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)

async function onRun() {
  if (!selected.value.length) {
    ElMessage.warning('请至少选择一条已确认用例')
    return
  }
  starting.value = true
  try {
    const payload = confirmed.value
      .filter((c) => selected.value.includes(c.id))
      .map((c) => ({ id: c.id, version: c.version }))
    const res = await startRun(projectId(), { cases: payload })
    ElMessage.success(`运行已发起（${res.status}）`)
    router.push(`/projects/${projectId()}/runs/${res.run_id}`)
  } catch (e) {
    ElMessage.error((e as Error).message || '发起运行失败')
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

    <div class="summary mt16">
      <div>
        <div class="summary-label">测试目标</div>
        <div class="summary-value">项目 {{ projectId() }} · 已确认用例 {{ confirmed.length }} 条</div>
      </div>
      <el-button type="primary" size="large" :loading="starting" @click="onRun">
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
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'CONFIRMED' ? 'success' : 'info'" size="small" effect="plain">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="mt16 hint">
      <el-text type="info" size="small">
        整批 1–20 条、每例 1–5 步；过期版本、未确认或引用失效将被整批拒绝。仅允许一个运行中批次。
      </el-text>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 900px;
}
.mt16 {
  margin-top: 16px;
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
