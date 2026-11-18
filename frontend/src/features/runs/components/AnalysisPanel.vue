<script setup lang="ts">
// 失败分析面板：用户点击触发，展示 category/reason/evidence/suggestion。
import { ref } from 'vue'
import { getAnalysis } from '@/api/runs'
import type { Analysis } from '@/api/types'

const props = defineProps<{ projectId: string; runId: string; caseId: string; outcome: string }>()

const loading = ref(false)
const analysis = ref<Analysis | null>(null)
const error = ref<string | null>(null)

async function run() {
  loading.value = true
  error.value = null
  try {
    analysis.value = await getAnalysis(props.projectId, props.runId, props.caseId)
  } catch (e) {
    error.value = (e as Error).message || '分析失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="analysis-panel">
    <el-button
      size="small"
      type="warning"
      plain
      :loading="loading"
      :disabled="outcome === 'PASS'"
      @click="run"
    >
      AI 失败分析
    </el-button>

    <el-alert v-if="error" :title="error" type="error" :closable="false" class="mt8" />

    <div v-if="analysis" class="analysis-result">
      <div class="cat"><el-tag type="warning" effect="dark">{{ analysis.category }}</el-tag></div>
      <div class="reason">{{ analysis.reason }}</div>
      <div v-if="analysis.evidence && analysis.evidence.length" class="evidence">
        <div class="label">证据</div>
        <ul>
          <li v-for="(e, i) in analysis.evidence" :key="i">{{ e }}</li>
        </ul>
      </div>
      <div v-if="analysis.suggestion" class="suggestion">
        <div class="label">建议</div>
        <div>{{ analysis.suggestion }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.analysis-panel {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e5e6eb;
}
.analysis-result {
  margin-top: 10px;
  padding: 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
}
.cat {
  margin-bottom: 6px;
}
.reason {
  font-size: 13px;
  color: #1f2329;
}
.evidence,
.suggestion {
  margin-top: 8px;
}
.label {
  font-size: 12px;
  font-weight: 700;
  color: #92400e;
  margin-bottom: 4px;
}
.evidence ul {
  margin: 0;
  padding-left: 18px;
}
.evidence li {
  font-size: 12px;
  color: #78350f;
  font-family: ui-monospace, Consolas, monospace;
}
.suggestion {
  font-size: 13px;
  color: #78350f;
}
.mt8 {
  margin-top: 8px;
}
</style>
