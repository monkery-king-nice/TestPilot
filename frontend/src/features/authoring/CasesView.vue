<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  confirmCase, generateCases, listEndpoints, listRequirements, saveCase,
  type BasisReview, type Endpoint, type Requirement,
} from '@/api/authoring'
import { assertionLabel, inputShape, reviewLabel } from './review.mjs'
import { confirmModelInput } from './modelConsent'
import { listCases } from '@/api/runs'
import type { Case, CaseDraft } from '@/api/types'

const route = useRoute()
const project = String(route.params.projectId)
const requirements = ref<Requirement[]>([])
const endpoints = ref<Endpoint[]>([])
const requirementId = ref(String(route.query.requirement ?? ''))
const cases = ref<Case[]>([])
const candidates = ref<CaseDraft[]>([])
const reviews = ref<BasisReview[]>([])
const editor = ref<CaseDraft | null>(null)
const editId = ref<string>()
const stepsText = ref('')
const busy = ref(false)
const error = ref('')
const notice = ref('')
const selectedRequirement = computed(() => requirements.value.find(item => item.id === requirementId.value))

async function perform(operation: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await operation()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '操作未完成'
  } finally {
    busy.value = false
  }
}

onMounted(() => perform(async () => {
  const [loadedCases, loadedRequirements, loadedEndpoints] = await Promise.all([
    listCases(project), listRequirements(project), listEndpoints(project),
  ])
  cases.value = loadedCases
  requirements.value = loadedRequirements
  endpoints.value = loadedEndpoints
  if (!selectedRequirement.value) requirementId.value = loadedRequirements[0]?.id ?? ''
}))

function openDraft(draft: CaseDraft, id?: string) {
  editId.value = id
  editor.value = {
    title: draft.title, expected_basis: draft.expected_basis,
    requirement_id: draft.requirement_id, requirement_version: draft.requirement_version,
    steps: draft.steps,
  }
  stepsText.value = JSON.stringify(draft.steps, null, 2)
}

function endpointLabel(id: string) {
  const ep = endpoints.value.find(item => item.id === id)
  return ep ? ep.method + ' ' + ep.path : '请核对接口'
}

function newDraft() {
  const req = selectedRequirement.value
  if (!req) return
  const endpoint = endpoints.value[0]
  openDraft({
    title: '', expected_basis: '', requirement_id: req.id, requirement_version: req.version,
    steps: endpoint ? [{
      name: 'check', phase: 'test', endpoint_id: endpoint.id, endpoint_version: endpoint.version,
      headers: {}, body: null, assertions: [{ type: 'status', expected: 200 }], extract: {},
    }] : [],
  })
}

function generate() {
  return perform(async () => {
    const requirement = selectedRequirement.value
    if (!requirement) return
    const digest = await confirmModelInput(project, requirement.id, requirement.version)
    if (!digest) return
    candidates.value = []
    const result = await generateCases(project, requirement.id, requirement.version, digest)
    candidates.value = result.drafts
    reviews.value = result.reviews ?? []
    notice.value = '请逐条核对预期，选择候选编辑并保存。'
  })
}

function saveDraft() {
  return perform(async () => {
    if (!editor.value) return
    let steps
    try { steps = JSON.parse(stepsText.value) }
    catch { throw new Error('步骤 JSON 格式不正确，请检查后再保存。') }
    if (!Array.isArray(steps)) throw new Error('步骤必须是 JSON 数组。')
    const item = await saveCase(project, { ...editor.value, steps }, editId.value)
    setCase(item)
    openDraft(item, item.id)
    notice.value = '已保存 v' + item.version + '。请核对后确认。'
  })
}

function setCase(item: Case) {
  const index = cases.value.findIndex(old => old.id === item.id)
  if (index < 0) cases.value.push(item)
  else cases.value[index] = item
}

function confirm(item: Case) {
  return perform(async () => {
    try {
      setCase(await confirmCase(project, item.id, item.version))
    } catch (cause) {
      cases.value = await listCases(project)
      throw cause
    }
    notice.value = '已确认「' + item.title + '」v' + item.version
  })
}

function useLatestRequirement() {
  const draft = editor.value
  if (!draft) return
  const latest = requirements.value.find(item => item.id === draft.requirement_id)
  if (latest) draft.requirement_version = latest.version
}
</script>

<template>
  <section class="case-workspace">
    <h1>测试用例</h1>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />
    <el-alert v-if="notice" :title="notice" type="success" :closable="false" />
    <el-card shadow="never">
      <template #header>候选用例</template>
      <div class="actions">
        <el-select v-model="requirementId" placeholder="选择需求" aria-label="选择需求"
          :disabled="busy" @change="candidates = []">
          <el-option v-for="item in requirements" :key="item.id" :value="item.id"
            :label="'v' + item.version + ' · ' + item.text.slice(0, 55)" />
        </el-select>
        <el-button type="primary" :loading="busy" :disabled="!selectedRequirement || !endpoints.length" @click="generate">生成候选用例</el-button>
        <el-button :disabled="busy || !selectedRequirement" @click="newDraft">手工新建</el-button>
      </div>
      <p v-if="!endpoints.length">请先在需求页登记接口。</p>
      <ul v-if="candidates.length">
        <li v-for="(draft, index) in candidates" :key="index">
          <strong>{{ draft.title }}</strong> · {{ draft.steps.length }} 个 HTTP 步骤
          <p>预期依据：{{ draft.expected_basis }}</p>
          <small>{{ reviewLabel(reviews[index]) }}</small>
          <ol>
            <li v-for="(step, s) in draft.steps" :key="s">
              {{ step.phase === 'setup' ? '准备' : '验证' }} · {{ endpointLabel(step.endpoint_id) }}
              <div>输入：{{ inputShape(step.body) }}</div>
              <div v-for="(a, n) in step.assertions" :key="n">{{ assertionLabel(a) }}</div>
            </li>
          </ol>
          <el-button link type="primary" :disabled="busy" @click="openDraft(draft)">编辑候选</el-button>
        </li>
      </ul>
    </el-card>
    <el-card v-if="editor" shadow="never">
      <template #header>{{ editId ? '编辑用例' : '编辑草稿' }}</template>
      <el-form label-position="top" :disabled="busy" @submit.prevent="saveDraft">
        <el-form-item label="用例标题"><el-input v-model="editor.title" maxlength="200" /></el-form-item>
        <el-form-item label="预期依据"><el-input v-model="editor.expected_basis" type="textarea" :rows="2" /></el-form-item>
        <p>关联需求 v{{ editor.requirement_version }}
          <el-button link type="primary" @click="useLatestRequirement">复核后采用最新需求版本</el-button>
        </p>
        <el-form-item label="步骤 JSON">
          <el-input v-model="stepsText" type="textarea" :rows="12" class="steps" />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="busy" :disabled="!editor.title.trim()">保存用例</el-button>
        <el-button @click="editor = null">关闭编辑</el-button>
      </el-form>
    </el-card>
    <el-card shadow="never">
      <template #header>已保存的用例</template>
      <el-empty v-if="!cases.length" description="暂无用例" />
      <ul v-else class="case-list">
        <li v-for="item in cases" :key="item.id">
          <strong>{{ item.title }}</strong> · v{{ item.version }} · <el-tag>{{ item.status }}</el-tag>
          <el-button link type="primary" :disabled="busy" @click="openDraft(item, item.id)">编辑用例</el-button>
          <el-button link type="success" :disabled="busy || !['READY', 'NEEDS_REVIEW'].includes(item.status) || !!item.reasons?.length"
            @click="confirm(item)">确认 v{{ item.version }}</el-button>
          <ul v-if="item.reasons?.length"><li v-for="reason in item.reasons" :key="reason">{{ reason }}</li></ul>
        </li>
      </ul>
      <router-link :to="{ name: 'runs-environment', params: { projectId: project } }">环境配置</router-link>
      <router-link v-if="cases.some(item => item.status === 'CONFIRMED')" class="run-link"
        :to="{ name: 'runs-list', params: { projectId: project } }">前往执行页</router-link>
    </el-card>
  </section>
</template>

<style scoped>
.case-workspace { max-width: 920px; display: grid; gap: 16px; margin: 0 auto; }
.case-workspace h1 { margin-bottom: 0; }
.actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.actions .el-select { width: min(100%, 400px); }
.case-list > li { margin-bottom: 12px; }
.run-link { margin-left: 20px; }
.steps :deep(textarea) { font-family: Consolas, monospace; }
</style>
