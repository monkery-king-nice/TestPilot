<script setup lang="ts">
// 单条用例结果卡片：标题 + 结果标签 + 步骤明细 + 失败分析入口。
import { computed } from 'vue'
import type { RunResult } from '@/api/types'
import { outcomeMeta } from '../outcomes'
import StepResultTable from './StepResultTable.vue'
import AnalysisPanel from './AnalysisPanel.vue'

const props = defineProps<{ result: RunResult; projectId: string; runId: string }>()

const meta = computed(() => outcomeMeta(props.result.outcome))

const canAnalyze = computed(() => props.result.outcome !== 'PASS')
</script>

<template>
  <el-card shadow="never" class="case-card" :body-style="{ padding: '16px' }">
    <template #header>
      <div class="case-header">
        <div class="case-title">
          <span class="case-id">#{{ result.case_id }}</span>
          <span class="title-text">{{ result.title }}</span>
        </div>
        <el-tag :color="meta.bg" :style="{ color: meta.color, borderColor: meta.color }" effect="plain" size="large">
          {{ result.outcome }}
        </el-tag>
      </div>
    </template>

    <StepResultTable :steps="result.steps" />

    <AnalysisPanel
      v-if="canAnalyze"
      :project-id="projectId"
      :run-id="runId"
      :case-id="result.case_id"
      :outcome="result.outcome"
    />
  </el-card>
</template>

<style scoped>
.case-card {
  margin-bottom: 14px;
}
.case-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.case-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.case-id {
  color: #94a3b8;
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  white-space: nowrap;
}
.title-text {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
