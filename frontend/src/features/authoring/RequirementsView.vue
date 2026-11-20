<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { HttpError } from '@/api/client'
import { readRequirementFile } from './requirementFile'
import { composeSupplement } from './requirementAnswers'
import ProjectImport from './ProjectImport.vue'
import {
  clarifyRequirement, createEndpoint, createRequirement, listEndpoints, listRequirements,
  updateRequirement, type Clarification, type Endpoint, type Requirement, type RequirementSource, type DocumentPreview,
} from '@/api/authoring'

const route = useRoute()
const router = useRouter()
const project = String(route.params.projectId)
const requirements = ref<Requirement[]>([])
const endpoints = ref<Endpoint[]>([])
const selected = ref('')
const text = ref('')
const source = ref<RequirementSource>()
const importBusy = ref(false)
const working = computed(() => busy.value || importBusy.value)
const answers = ref<string[]>([])
const clarificationVersion = ref<number>()
const conflict = ref(false)
const supplementPreview = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const method = ref('POST')
const path = ref('')
const busy = ref(false)
const error = ref('')
const clarification = ref<Clarification | null>(null)
const saved = computed(() => requirements.value.find(item => item.id === selected.value))
const edited = computed(() => text.value !== (saved.value?.text ?? ''))
const hasUnsaved = computed(() => edited.value || answers.value.some(answer => answer.trim()))

let leaveDecision: Promise<boolean> | undefined
async function decideLeave(): Promise<boolean> {
  try {
    await ElMessageBox.confirm('需求原文或补充答案尚未保存。可以保存后离开，或确认放弃。关闭此窗口可继续编辑。', '未保存的需求或答案', {
      confirmButtonText: '保存后离开', cancelButtonText: '放弃并离开',
      distinguishCancelAndClose: true, closeOnClickModal: false, type: 'warning',
    })
    await save()
    return !hasUnsaved.value && !working.value && !conflict.value
  } catch (action) { return action === 'cancel' }
}

onBeforeRouteLeave(to => {
  if (working.value) return false
  if (!hasUnsaved.value) return true
  if (!leaveDecision) leaveDecision = decideLeave().finally(() => { leaveDecision = undefined })
  return leaveDecision.then(allowed => {
    if (allowed && !hasUnsaved.value && to.name === 'cases' && saved.value && to.query.requirement !== saved.value.id) {
      return { name: 'cases', params: to.params, query: { ...to.query, requirement: saved.value.id } }
    }
    return allowed
  })
})

function beforeUnload(event: BeforeUnloadEvent) {
  if (hasUnsaved.value || working.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload))

function select(id: string, preserveImport = false) {
  selected.value = id
  text.value = saved.value?.text ?? ''
  source.value = saved.value?.source
  clarification.value = null
  answers.value = []
  clarificationVersion.value = undefined
  supplementPreview.value = ''
  conflict.value = false
  if (!leaveDecision) void router.replace({ query: {
    ...route.query, requirement: id || undefined,
    import: preserveImport ? route.query.import || saved.value?.source?.import_id : saved.value?.source?.import_id || route.query.import,
  } })
}

function resetQuestions() {
  clarification.value = null
  answers.value = []
  supplementPreview.value = ''
}

async function canReplace() {
  if (!hasUnsaved.value) return true
  try {
    await ElMessageBox.confirm('将替换尚未保存的原文或答案。是否继续？', '替换未保存内容', {
      confirmButtonText: '替换内容', cancelButtonText: '保留原稿', type: 'warning',
    })
    return true
  } catch { return false }
}

async function changeSelection(id: string) {
  return perform(async () => { if (await canReplace()) select(id) })
}

async function perform(operation: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await operation()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '操作未完成'
    if (cause instanceof HttpError && cause.status === 409) {
      conflict.value = true
      error.value += '。原稿和答案已保留，请查看最新需求后重新复核。'
    }
  } finally {
    busy.value = false
  }
}

onMounted(() => perform(async () => {
  const [loadedRequirements, loadedEndpoints] = await Promise.all([
    listRequirements(project), listEndpoints(project),
  ])
  requirements.value = loadedRequirements
  endpoints.value = loadedEndpoints
  const requested = String(route.query.requirement ?? '')
  select(requirements.value.find(item => item.id === requested)?.id ?? requirements.value[0]?.id ?? '', true)
}))

function save() {
  if (clarification.value && answers.value.some(answer => answer.trim())) return saveSupplement()
  return perform(async () => {
    const item = selected.value
      ? await updateRequirement(project, selected.value, text.value, saved.value?.version)
      : await createRequirement(project, text.value, source.value)
    requirements.value = [
      ...requirements.value.filter(old => old.id !== item.id), item,
    ]
    select(item.id)
  })
}

function importFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  return perform(async () => {
    const content = await readRequirementFile(file)
    if (!await canReplace()) return
    if (source.value) select('')
    text.value = content
    resetQuestions()
  })
}

function useDocument(preview: DocumentPreview) {
  return perform(async () => {
    if (!await canReplace()) return
    select('')
    const { import_id, path, start, end } = preview
    source.value = { import_id, path, start, end }
    text.value = preview.text
  })
}

function loadLatest() {
  return perform(async () => {
    const latest = await listRequirements(project)
    if (!await canReplace()) return
    requirements.value = latest
    select(selected.value)
  })
}

function previewSupplement() {
  try {
    error.value = ''
    supplementPreview.value = composeSupplement(text.value, clarificationVersion.value!, clarification.value!.questions, answers.value)
  } catch (cause) { error.value = (cause as Error).message }
}

function saveSupplement() {
  return perform(async () => {
    const version = clarificationVersion.value
    if (!clarification.value || !version) throw new Error('请先保存原文，再重新检查缺项')
    const combined = composeSupplement(text.value, version, clarification.value.questions, answers.value)
    const item = await updateRequirement(project, selected.value, combined, version)
    requirements.value = requirements.value.map(old => old.id === item.id ? item : old)
    select(item.id)
  })
}

function clarify() {
  return perform(async () => {
    if (answers.value.some(answer => answer.trim()) && !await canReplace()) return
    clarification.value = null
    const result = await clarifyRequirement(project, selected.value, saved.value!.version)
    clarification.value = result
    clarificationVersion.value = saved.value!.version
    answers.value = result.questions.map(() => '')
    supplementPreview.value = ''
  })
}

function addEndpoint() {
  return perform(async () => {
    endpoints.value.push(await createEndpoint(project, method.value, path.value.trim()))
    path.value = ''
  })
}

function reloadEndpoints() {
  return perform(async () => { endpoints.value = await listEndpoints(project) })
}
</script>

<template>
  <section class="authoring-section">
    <h1>需求管理</h1>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-button v-if="conflict" :disabled="working" @click="loadLatest">查看最新需求</el-button>
    <ProjectImport :project-id="project" :import-id="source?.import_id" :disabled="busy"
      @busy="importBusy = $event" @preview="useDocument" @endpoints="reloadEndpoints" />
    <el-card shadow="never">
      <template #header>需求原文</template>
      <div class="controls">
        <el-select :model-value="selected" aria-label="选择需求" :disabled="working" @change="changeSelection">
          <el-option label="新需求" value="" />
          <el-option v-for="item in requirements" :key="item.id" :value="item.id"
            :label="'v' + item.version + ' · ' + item.text.slice(0, 55)" />
        </el-select>
        <span v-if="saved">已保存版本 v{{ saved.version }}</span>
        <input ref="fileInput" type="file" accept=".md,.txt" hidden @change="importFile" />
        <el-button :disabled="working" @click="fileInput?.click()">从文件导入</el-button>
      </div>
      <p v-if="source">原始来源 {{ source.path }} · 字符 {{ source.start }}–{{ source.end }}</p>
      <p class="import-help">支持 UTF-8 编码的 Markdown、TXT，最多 16000 字符。导入后可预览和修改，点击“保存需求”后保存。</p>
      <div class="requirement-review" :class="{ 'has-questions': clarification?.questions.length }">
      <div>
      <el-input v-model="text" type="textarea" :rows="7" maxlength="16000"
        aria-label="需求原文" placeholder="录入需要测试的行为和预期结果" :disabled="working"
        @input="supplementPreview = ''" />
      <div class="controls">
        <el-button type="primary" :loading="busy" :disabled="working || !text.trim() || !edited || conflict" @click="save">保存需求</el-button>
        <el-button :disabled="working || !saved || edited || conflict" @click="clarify">检查缺项</el-button>
        <router-link v-if="saved && !edited" :to="{ name: 'cases', params: { projectId: project }, query: { requirement: saved.id } }">
          去测试用例页
        </router-link>
      </div>
      </div>
      <div v-if="clarification">
        <el-alert v-if="clarification.status === 'READY'" title="当前范围无需继续追问" type="success" :closable="false" />
        <ol v-else aria-label="需求追问">
          <li v-for="(item, index) in clarification.questions" :key="item.quote + item.question">
            <blockquote>{{ item.quote }}</blockquote>
            <small>来源 {{ item.source_path || source?.path || ('已保存需求 v' + clarificationVersion) }}</small>
            <p>{{ item.question }}</p>
            <el-input v-model="answers[index]" type="textarea" :rows="3" :aria-label="'补充答案 ' + (index + 1)"
              :disabled="working" @input="supplementPreview = ''" />
          </li>
        </ol>
        <el-alert v-if="clarification.dropped" type="info" :closable="false" show-icon
          :title="'另有 ' + clarification.dropped + ' 条追问的引用无法在原文中定位，已略去（可精简需求后重试）'" />
        <div v-if="clarification.questions.length" class="controls">
          <el-button :disabled="working || !answers.some(answer => answer.trim())" @click="previewSupplement">预览补充</el-button>
          <el-button type="primary" :disabled="working || conflict || !answers.some(answer => answer.trim())" @click="saveSupplement">保存补充为新版本</el-button>
        </div>
        <pre v-if="supplementPreview" class="supplement-preview">{{ supplementPreview }}</pre>
      </div>
      </div>
    </el-card>
    <el-card shadow="never">
      <template #header>已登记接口</template>
      <ul v-if="endpoints.length">
        <li v-for="endpoint in endpoints" :key="endpoint.id">
          <code>{{ endpoint.method }} {{ endpoint.path }}</code> · v{{ endpoint.version }}
        </li>
      </ul>
      <form class="controls" @submit.prevent="addEndpoint">
        <el-select v-model="method" aria-label="HTTP 方法" :disabled="working">
          <el-option v-for="item in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']" :key="item" :label="item" :value="item" />
        </el-select>
        <el-input v-model="path" placeholder="/auth/login" aria-label="相对接口路径" :disabled="working" />
        <el-button native-type="submit" :disabled="working || !path.trim()">登记接口</el-button>
      </form>
    </el-card>
  </section>
</template>

<style scoped>
.authoring-section { max-width: 920px; display: grid; gap: 16px; margin: 0 auto; }
.authoring-section h1 { margin-bottom: 0; }
.controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0; }
.controls :is(.el-select, .el-input) { width: min(100%, 300px); }
blockquote { border-left: 3px solid #dbeafe; margin: 12px 0 0; padding-left: 12px; color: #475569; }
.import-help { color: #475569; font-size: 14px; line-height: 1.6; }
li p { margin: 5px 0 12px; }
.supplement-preview { white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; background: #f5f7fa; }
.requirement-review { display: grid; gap: 20px; }
.requirement-review.has-questions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.supplement-preview { max-height: 320px; overflow-y: auto; }
@media (max-width: 760px) { .requirement-review.has-questions { grid-template-columns: minmax(0, 1fr); } }
</style>
