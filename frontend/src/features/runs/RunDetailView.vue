<script setup lang="ts">
// 运行详情页：轮询 RunDetail，展示四类统计、逐用例步骤断言差异、错误阶段与脱敏证据；提供 HTML 下载。
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getReportHtml } from '@/api/runs'
import type { RunStatus } from '@/api/types'
import { useRunPolling } from './composables/useRunPolling'
import OutcomeStats from './components/OutcomeStats.vue'
import CaseResultCard from './components/CaseResultCard.vue'

const route = useRoute()
const router = useRouter()
const projectId = () => String(route.params.projectId)
const runId = () => String(route.params.runId)

const { detail, loading, polling, error, restore } = useRunPolling()

watch([projectId, runId], ([project, run]) => restore(project, run), { immediate: true })

const statusTag = computed(() => {
  const map: Record<RunStatus, { type: 'info' | 'primary' | 'success' | 'warning'; text: string }> = {
    QUEUED: { type: 'info', text: '排队中' },
    RUNNING: { type: 'primary', text: '运行中' },
    COMPLETED: { type: 'success', text: '已完成' },
    INTERRUPTED: { type: 'warning', text: '已中断' }
  }
  return map[detail.value?.status ?? 'QUEUED']
})

const downloading = ref(false)

async function downloadReport() {
  if (!detail.value) return
  downloading.value = true
  try {
    const html = await getReportHtml(projectId(), runId())
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `testpilot-report-${runId()}.html`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    ElMessage.success('报告已下载')
  } catch (e) {
    ElMessage.error((e as Error).message || '下载报告失败')
  } finally {
    downloading.value = false
  }
}

function goEnvironment() {
  router.push(`/projects/${projectId()}/environment`)
}
</script>

<template>
  <div class="page">
    <el-page-header @back="router.push(`/projects/${projectId()}/run`)" title="返回执行页">
      <template #content>
        <span class="ph-title">运行详情</span>
      </template>
      <template #extra>
        <el-button size="small" :loading="downloading" :disabled="!detail" @click="downloadReport">
          下载 HTML 报告
        </el-button>
      </template>
    </el-page-header>

    <div v-if="error" class="mt16">
      <el-alert :title="error" type="error" :closable="false" show-icon />
    </div>

    <div v-if="detail" class="mt16">
      <div class="run-head">
        <div>
          <div class="run-id">批次 <span class="mono">{{ detail.run_id }}</span></div>
          <div class="run-status">
            <el-tag :type="statusTag.type" size="large" effect="dark">
              <span v-if="polling" class="spin">⟳</span> {{ statusTag.text }}（{{ detail.status }}）
            </el-tag>
          </div>
        </div>
        <el-button v-if="!polling && detail.status !== 'COMPLETED'" size="small" @click="restore(projectId(), runId())">
          刷新
        </el-button>
      </div>

      <OutcomeStats :detail="detail" class="mt16" />

      <div class="mt16 section-title">用例结果</div>
      <CaseResultCard
        v-for="r in detail.results"
        :key="r.case_id"
        :result="r"
        :project-id="projectId()"
        :run-id="runId()"
      />
    </div>

    <el-skeleton v-else-if="loading" :rows="6" animated class="mt16" />

    <div class="mt16 hint">
      <el-text type="info" size="small">
        报告与 AI 分析读取同一份冻结证据；模型不可用时结果与下载仍可用。准备失败（setup 未通过）显示 BLOCKED。
        <el-link type="primary" :underline="false" @click="goEnvironment">前往环境配置 →</el-link>
      </el-text>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 1080px;
}
.mt16 {
  margin-top: 16px;
}
.ph-title {
  font-weight: 600;
}
.run-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}
.run-id {
  font-size: 13px;
  color: #64748b;
}
.mono {
  font-family: ui-monospace, Consolas, monospace;
}
.run-status {
  margin-top: 8px;
}
.spin {
  display: inline-block;
  animation: spin 1s linear infinite;
  margin-right: 2px;
}
@keyframes spin {
  from {
    transform: rotate(0);
  }
  to {
    transform: rotate(360deg);
  }
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}
.hint {
  text-align: right;
}
</style>
