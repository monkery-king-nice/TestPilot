<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  uploadProject, getProjectImport, previewDocument, confirmImportEndpoints,
  type ProjectImport, type DocumentPreview,
} from '@/api/authoring'

const props = defineProps<{ projectId: string; importId?: string; disabled: boolean }>()
const emit = defineEmits<{
  preview: [DocumentPreview]; endpoints: []; busy: [boolean]
}>()
const route = useRoute()
const router = useRouter()
const manifest = ref<ProjectImport>()
const preview = ref<DocumentPreview>()
const fileInput = ref<HTMLInputElement | null>(null)
const documentPath = ref('')
const start = ref(0)
const end = ref<number>()
const candidates = ref<string[]>([])
const busy = ref(false)
const error = ref('')
const chosenImport = computed(() => String(route.query.import ?? '') || props.importId || '')
const confirmed = (id: string) => manifest.value?.confirmed_endpoints.some(item => item.candidate_id === id)

async function perform(operation: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  emit('busy', true)
  error.value = ''
  try { await operation() }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '导入失败，请重试或手工录入需求与接口' }
  finally { busy.value = false; emit('busy', false) }
}

watch(chosenImport, id => {
  if (!id || id === manifest.value?.id) return
  void perform(async () => {
    manifest.value = await getProjectImport(props.projectId, id)
    documentPath.value = ''
    preview.value = undefined
    candidates.value = []
  })
}, { immediate: true })

function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  return perform(async () => {
    if (!/\.zip$/i.test(file.name)) throw new Error('请选择 ZIP 项目包，或在下方单独导入 MD/TXT')
    if (file.size > 40 * 1024 * 1024) throw new Error('ZIP 最多 40 MiB，请精简项目包后重试')
    const result = await uploadProject(props.projectId, file)
    manifest.value = result
    documentPath.value = ''
    preview.value = undefined
    candidates.value = []
    await router.replace({ query: { ...route.query, import: result.id } })
  })
}

function loadPreview() {
  return perform(async () => {
    if (!manifest.value) return
    const result = await previewDocument(props.projectId, manifest.value.id, documentPath.value, start.value, end.value)
    preview.value = result
  })
}

function register() {
  return perform(async () => {
    if (!manifest.value) return
    await confirmImportEndpoints(props.projectId, manifest.value.id, candidates.value)
    emit('endpoints')
    // Reload confirmation state from the server, including on repeated confirmation.
    manifest.value = await getProjectImport(props.projectId, manifest.value.id)
    candidates.value = []
  })
}
</script>

<template>
  <el-card shadow="never">
    <template #header>项目资料</template>
    <input ref="fileInput" type="file" accept=".zip" hidden @change="upload" />
    <el-button :disabled="disabled || busy" @click="fileInput?.click()">上传项目 ZIP</el-button>
    <p>可上传需求与接口说明的精简 ZIP（最多 40 MiB），也可直接在下方填写。原包会保存到此实例，请移除密钥与真实用户数据。</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <div v-if="manifest">
      <p role="status">已上传 {{ manifest.filename }} · {{ manifest.documents.length }} 份可选文档 · {{ manifest.endpoint_candidates.length }} 个候选接口 · 本包已确认 {{ manifest.confirmed_endpoints.length }} 个</p>
      <el-alert v-for="warning in manifest.warnings" :key="warning" :title="warning" type="warning" :closable="false" />
      <p v-if="!manifest.documents.length">包内没有可选需求文档，请在下方单独导入 MD/TXT，或手工输入需求。</p>
      <form v-else class="import-controls" @submit.prevent="loadPreview">
        <el-select v-model="documentPath" aria-label="包内需求文档" placeholder="选择需求文档"
          :disabled="disabled || busy" @change="preview = undefined; start = 0; end = undefined">
          <el-option v-for="doc in manifest.documents" :key="doc.path" :label="doc.path" :value="doc.path" />
        </el-select>
        <label>起始字符 <el-input-number v-model="start" aria-label="片段起始字符" :min="0" :precision="0" :disabled="disabled || busy" /></label>
        <label>结束字符 <el-input-number v-model="end" aria-label="片段结束字符" :min="1" :precision="0" :disabled="disabled || busy" /></label>
        <el-button native-type="submit" :disabled="disabled || busy || !documentPath">预览文档</el-button>
      </form>
      <p v-if="manifest.documents.length">字符位置从 0 起，结束位置不计入片段。结束字符留空时最多预览 16000 字符。</p>
      <div v-if="preview">
        <p>{{ preview.path }} · 字符 {{ preview.start }}–{{ preview.end }} / {{ preview.total_chars }}</p>
        <p v-if="preview.end < preview.total_chars">当前仅预览部分内容，可调整字符范围，每段最多 16000 字符。</p>
        <pre class="document-preview">{{ preview.text }}</pre>
        <el-button :disabled="disabled || busy" @click="emit('preview', preview)">作为新需求原文</el-button>
      </div>
      <h3>候选接口</h3>
      <p v-if="manifest.needs_manual_endpoints">请检查下方候选和解析提示。若项目已有 HTTP 服务，请在下方手工登记实际接口和具体路径；仅有文档也可先保存需求、检查缺项。</p>
      <el-checkbox-group v-model="candidates" aria-label="候选接口" :disabled="disabled || busy">
        <div v-for="candidate in manifest.endpoint_candidates" :key="candidate.candidate_id" class="candidate">
          <el-checkbox :value="candidate.candidate_id" :disabled="candidate.requires_manual_registration || confirmed(candidate.candidate_id)">
            {{ candidate.method }} {{ candidate.path }} {{ candidate.summary }}
          </el-checkbox>
          <span v-if="confirmed(candidate.candidate_id)">已登记</span>
          <p>来源 {{ candidate.source_path }}</p>
          <p v-if="candidate.requires_manual_registration">含路径参数，请在下方填写具体路径后手工登记。</p>
          <p v-if="candidate.request_fields?.length">JSON 输入：{{ candidate.request_fields.map(f => f.name + (f.required ? "（必填）" : "（选填）")).join("、") }}</p>
          <ul v-if="candidate.parameters?.length">
            <li v-for="parameter in candidate.parameters" :key="parameter.in + parameter.name">
              {{ parameter.in }} · {{ parameter.name }} {{ parameter.required ? '必填' : '选填' }} {{ parameter.description }}
            </li>
          </ul>
          <p v-for="response in candidate.responses" :key="response.status">{{ response.status }} {{ response.description }}</p>
        </div>
      </el-checkbox-group>
      <el-button v-if="manifest.endpoint_candidates.length" :disabled="disabled || busy || !candidates.length" @click="register">确认登记所选接口</el-button>
    </div>
  </el-card>
</template>

<style scoped>
.import-controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 16px 0; }
.el-select { width: min(100%, 320px); }
.document-preview { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 240px; overflow-y: auto; padding: 12px; background: #f5f7fa; }
.candidate { font-size: 14px; line-height: 1.6; border-bottom: 1px solid #e5e7eb; padding: 10px 0; }
.candidate > span { margin-left: 8px; }
.candidate .el-checkbox { height: auto; white-space: normal; }
.candidate p { margin: 6px 0; }
p { line-height: 1.6; }
</style>
