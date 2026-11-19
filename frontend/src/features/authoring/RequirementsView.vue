<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { readRequirementFile } from './requirementFile'
import {
  clarifyRequirement, createEndpoint, createRequirement, listEndpoints, listRequirements,
  updateRequirement, type Clarification, type Endpoint, type Requirement,
} from '@/api/authoring'

const project = String(useRoute().params.projectId)
const requirements = ref<Requirement[]>([])
const endpoints = ref<Endpoint[]>([])
const selected = ref('')
const text = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const method = ref('POST')
const path = ref('')
const busy = ref(false)
const error = ref('')
const clarification = ref<Clarification | null>(null)
const saved = computed(() => requirements.value.find(item => item.id === selected.value))
const edited = computed(() => text.value !== saved.value?.text)

function select(id: string) {
  selected.value = id
  text.value = saved.value?.text ?? ''
  clarification.value = null
}

async function perform(operation: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await operation()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '操作未完成'
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
  select(requirements.value[0]?.id ?? '')
}))

function save() {
  return perform(async () => {
    const item = selected.value
      ? await updateRequirement(project, selected.value, text.value)
      : await createRequirement(project, text.value)
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
    const source = await readRequirementFile(file)
    if (text.value !== (saved.value?.text ?? '')) {
      try {
        await ElMessageBox.confirm('导入文件会替换编辑框中尚未保存的内容。是否继续？', '替换未保存内容', {
          confirmButtonText: '替换内容', cancelButtonText: '保留原稿', type: 'warning',
        })
      } catch {
        return
      }
    }
    text.value = source
    clarification.value = null
  })
}

function clarify() {
  return perform(async () => {
    clarification.value = null
    clarification.value = await clarifyRequirement(project, selected.value)
  })
}

function addEndpoint() {
  return perform(async () => {
    endpoints.value.push(await createEndpoint(project, method.value, path.value.trim()))
    path.value = ''
  })
}
</script>

<template>
  <section class="authoring-section">
    <h1>需求管理</h1>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-card shadow="never">
      <template #header>需求原文</template>
      <div class="controls">
        <el-select :model-value="selected" aria-label="选择需求" :disabled="busy" @change="select">
          <el-option label="新需求" value="" />
          <el-option v-for="item in requirements" :key="item.id" :value="item.id"
            :label="'v' + item.version + ' · ' + item.text.slice(0, 55)" />
        </el-select>
        <span v-if="saved">已保存版本 v{{ saved.version }}</span>
        <input ref="fileInput" type="file" accept=".md,.txt" hidden @change="importFile" />
        <el-button :disabled="busy" @click="fileInput?.click()">从文件导入</el-button>
      </div>
      <p class="import-help">支持 UTF-8 编码的 Markdown、TXT，最多 16000 字符。导入后可预览和修改，点击“保存需求”后保存。</p>
      <el-input v-model="text" type="textarea" :rows="7" maxlength="16000"
        aria-label="需求原文" placeholder="录入需要测试的行为和预期结果" :disabled="busy"
        @input="clarification = null" />
      <div class="controls">
        <el-button type="primary" :loading="busy" :disabled="!text.trim() || !edited" @click="save">保存需求</el-button>
        <el-button :disabled="busy || !saved || edited" @click="clarify">检查缺项</el-button>
        <router-link v-if="saved && !edited" :to="{ name: 'cases', params: { projectId: project }, query: { requirement: saved.id } }">
          去测试用例页
        </router-link>
      </div>
      <div v-if="clarification">
        <el-alert v-if="clarification.status === 'READY'" title="当前范围无需继续追问" type="success" :closable="false" />
        <ol v-else aria-label="需求追问">
          <li v-for="item in clarification.questions" :key="item.quote + item.question">
            <blockquote>{{ item.quote }}</blockquote>
            <p>{{ item.question }}</p>
          </li>
        </ol>
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
        <el-select v-model="method" aria-label="HTTP 方法" :disabled="busy">
          <el-option v-for="item in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']" :key="item" :label="item" :value="item" />
        </el-select>
        <el-input v-model="path" placeholder="/auth/login" aria-label="相对接口路径" :disabled="busy" />
        <el-button native-type="submit" :disabled="busy || !path.trim()">登记接口</el-button>
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
</style>
