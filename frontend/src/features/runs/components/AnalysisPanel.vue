<script setup lang="ts">
// 失败分析面板：用户点击触发，展示 category/reason/evidence/suggestion。
// 组件在批次/用例之间会被复用：用请求键 + 序号保护，迟到的分析响应不会落到新对象上。
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getAnalysis, previewAnalysis } from '@/api/runs'
import { USE_MOCK } from '@/api/config'
import { confirmPreview } from '../../authoring/modelConsent'
import { useAnalysisRequest } from '../composables/useAnalysisRequest'

const props = defineProps<{ projectId: string; runId: string; caseId: string; outcome: string }>()

const { analysis, loading, error, reset, run: runRequest } = useAnalysisRequest()

const previewing = ref(false)

function requestKey(): string {
  return `${props.projectId}\u0000${props.runId}\u0000${props.caseId}`
}

// A→B 切换（可能复用同一 case_id 的组件）：清空旧分析并作废在途请求。
watch([() => props.projectId, () => props.runId, () => props.caseId], () => reset(requestKey()))

async function run() {
  // 点击瞬间固定目标对象，请求与结果都用这组值校验。
  const targetProjectId = props.projectId
  const targetRunId = props.runId
  const targetCaseId = props.caseId
  const key = `${targetProjectId}\u0000${targetRunId}\u0000${targetCaseId}`
  if (previewing.value || loading.value) return
  let digest: string | undefined
  if (!USE_MOCK) {
    previewing.value = true
    try {
      const preview = await previewAnalysis(targetProjectId, targetRunId, targetCaseId)
      if (requestKey() !== key || !(await confirmPreview(preview.context)) || requestKey() !== key) return
      digest = preview.digest
    } catch (e) {
      if (requestKey() === key) ElMessage.error((e as Error).message || '读取证据失败')
      return
    } finally {
      previewing.value = false
    }
  }
  await runRequest(key, () => getAnalysis(targetProjectId, targetRunId, targetCaseId, digest))
}
</script>

<template>
  <div class="analysis-panel">
    <p v-if="outcome !== 'PASS'">分析前可核对本次要发送的失败证据。</p>
    <el-button
      size="small"
      type="warning"
      plain
      :loading="loading || previewing"
      :disabled="outcome === 'PASS'"
      @click="run"
    >
      AI 失败分析
    </el-button>

    <el-alert v-if="error" :title="'模型分析失败：' + error" type="error" :closable="false" show-icon class="mt8" />

    <div v-if="analysis" class="analysis-result">
      <div class="cat"><el-tag type="warning" effect="dark">模型分析 · {{ analysis.category }}</el-tag></div>
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
