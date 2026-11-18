<script setup lang="ts">
// 单条用例的步骤执行明细：阶段、HTTP 状态、耗时、脱敏摘要、断言差异、错误阶段。
import type { RunStepResult, StepPhase } from '@/api/types'

defineProps<{ steps: RunStepResult[] }>()

const PHASE_LABEL: Record<StepPhase, string> = {
  setup: '准备',
  test: '测试',
  teardown: '清理'
}

function phaseTag(phase: StepPhase): 'info' | 'primary' | 'warning' {
  if (phase === 'setup') return 'info'
  if (phase === 'test') return 'primary'
  return 'warning'
}

function phaseLabel(phase: StepPhase): string {
  return PHASE_LABEL[phase] ?? String(phase)
}

function fmt(v: string | number | null): string {
  return v === null || v === undefined ? '—' : String(v)
}
</script>

<template>
  <el-table :data="steps" size="small" border>
    <el-table-column label="步骤" min-width="110">
      <template #default="{ row }">
        <div class="step-name">{{ row.name }}</div>
        <el-tag :type="phaseTag(row.phase)" size="small" effect="plain">{{ phaseLabel(row.phase) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="HTTP / 耗时" width="120" align="center">
      <template #default="{ row }">
        <div>{{ fmt(row.http_status) }}</div>
        <div class="muted">{{ row.elapsed_ms === null ? '—' : `${row.elapsed_ms} ms` }}</div>
      </template>
    </el-table-column>
    <el-table-column label="脱敏摘要" min-width="240">
      <template #default="{ row }">
        <div class="mono">req: {{ fmt(row.request_summary) }}</div>
        <div class="mono">res: {{ fmt(row.response_summary) }}</div>
      </template>
    </el-table-column>
    <el-table-column label="断言差异 / 错误阶段" min-width="220">
      <template #default="{ row }">
        <div v-if="row.assertion_diffs && row.assertion_diffs.length">
          <div v-for="(d, i) in row.assertion_diffs" :key="i" class="diff">✕ {{ d }}</div>
        </div>
        <div v-else class="ok">✓ 无差异</div>
        <el-tag v-if="row.error_stage" type="danger" size="small" class="error-stage">
          {{ row.error_stage }}
        </el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.step-name {
  font-weight: 600;
  margin-bottom: 4px;
}
.mono {
  font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
}
.muted {
  color: #6b7280;
  font-size: 12px;
}
.diff {
  color: #dc2626;
  font-size: 12px;
}
.ok {
  color: #16a34a;
  font-size: 12px;
}
.error-stage {
  margin-top: 6px;
}
</style>
