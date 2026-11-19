<script setup lang="ts">
// 环境页：选择执行目标（演示服务或项目已启动的本地服务），保存凭证后只显示字段名。
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useEnvironment } from './composables/useEnvironment'
import { credentialDecision } from './runContext.mjs'
import type { TargetKind } from '@/api/types'

const route = useRoute()
const router = useRouter()
const projectId = () => String(route.params.projectId)

const { target, serviceId, baseUrl, environmentVersion, configuredKeys, loading, saving, load, save } =
  useEnvironment(projectId)

const form = reactive({
  target: 'local' as TargetKind,
  serviceId: '',
  baseUrl: '',
  username: '',
  password: ''
})
const showPassword = ref(false)
const noCredentials = ref(false)
const isLocal = computed(() => form.target === 'local')
const hasSavedCredentials = computed(() => configuredKeys.value.length > 0)

// 切到演示服务时，「不使用凭据」不适用。
watch(
  () => form.target,
  (value) => {
    if (value === 'demo') noCredentials.value = false
  }
)
// 勾选「不使用凭据」时清空已输入的凭据，避免误以为会保存。
watch(noCredentials, (value) => {
  if (value) {
    form.username = ''
    form.password = ''
  }
})

onMounted(async () => {
  await load()
  form.target = target.value
  form.serviceId = serviceId.value ?? ''
  form.baseUrl = baseUrl.value ?? ''
})

const REASON_MESSAGE: Record<string, string> = {
  'demo-needs-both': '演示服务需要同时填写用户名和密码',
  'one-missing': '用户名和密码需要同时填写；如果该服务不需要登录，请勾选「不使用凭据」',
  'clear-needs-choice': '已有保存的凭据。如需清空，请先勾选「不使用凭据」'
}

async function onSubmit() {
  if (isLocal.value && (!form.serviceId.trim() || !form.baseUrl.trim())) {
    ElMessage.warning('本地服务需要填写服务标识与回环地址')
    return
  }
  const decision = credentialDecision({
    target: form.target,
    username: form.username,
    password: form.password,
    noCredentials: noCredentials.value,
    hasSavedCredentials: hasSavedCredentials.value
  })
  if (!decision.ok) {
    ElMessage.warning(REASON_MESSAGE[decision.reason ?? ''] ?? '请检查凭据填写')
    return
  }
  const write =
    form.target === 'local'
      ? {
          target: 'local' as const,
          service_id: form.serviceId.trim(),
          base_url: form.baseUrl.trim(),
          secrets: decision.secrets
        }
      : { target: 'demo' as const, secrets: decision.secrets! }
  await save(write)
  form.password = ''
  noCredentials.value = false
}

function goRun() {
  router.push(`/projects/${projectId()}/run`)
}
</script>

<template>
  <div class="page">
    <el-page-header @back="router.back()" title="返回">
      <template #content>
        <span class="ph-title">环境配置</span>
      </template>
    </el-page-header>

    <el-card class="mt16" shadow="never" :body-style="{ padding: '20px' }">
      <template #header>
        <div class="card-h">
          <span>执行目标与凭证</span>
          <el-tag type="info" effect="plain">目标：{{ target }}</el-tag>
        </div>
      </template>

      <el-alert
        title="选择「项目本地服务」时填写被测服务实际启动的回环地址；没有登录的本地服务可留空凭据。凭证值保存后不返回前端，仅服务端执行器可读取。"
        type="info"
        :closable="false"
        class="mb16"
      />

      <el-form label-width="100px" @submit.prevent>
        <el-form-item label="执行目标">
          <el-radio-group v-model="form.target">
            <el-radio-button label="local">项目本地服务</el-radio-button>
            <el-radio-button label="demo">团队演示服务</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="isLocal">
          <el-form-item label="服务标识">
            <el-input v-model="form.serviceId" placeholder="例如 项目A-8080" style="max-width: 320px" />
          </el-form-item>
          <el-form-item label="回环地址">
            <el-input v-model="form.baseUrl" placeholder="http://127.0.0.1:8080" style="max-width: 320px" />
          </el-form-item>
          <el-form-item label="凭据">
            <el-checkbox v-model="noCredentials">该服务不需要登录（不使用凭据）</el-checkbox>
          </el-form-item>
        </template>

        <el-form-item label="用户名">
          <el-input
            v-model="form.username"
            :disabled="noCredentials"
            placeholder="被测服务的登录账号（如需要）"
            style="max-width: 320px"
          />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            :disabled="noCredentials"
            :type="showPassword ? 'text' : 'password'"
            placeholder="被测服务的登录密码（如需要）"
            style="max-width: 320px"
          >
            <template #append>
              <el-button :disabled="noCredentials" @click="showPassword = !showPassword">
                {{ showPassword ? '隐藏' : '显示' }}
              </el-button>
            </template>
          </el-input>
        </el-form-item>
        <el-form-item v-if="isLocal && hasSavedCredentials && !noCredentials" label=" ">
          <el-text type="info" size="small">
            已保存凭据：重新填写两项可更新；如需清空，请勾选上方「不使用凭据」。
          </el-text>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onSubmit">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-loading="loading" class="mt16" shadow="never" :body-style="{ padding: '20px' }">
      <template #header>
        <div class="card-h">
          <span>已保存状态（不展示凭证值）</span>
          <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>

      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="目标类型">{{ target }}</el-descriptions-item>
        <el-descriptions-item label="环境版本">{{ environmentVersion ?? '未配置' }}</el-descriptions-item>
        <el-descriptions-item label="服务标识">{{ serviceId ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="服务地址">{{ baseUrl ?? '—' }}</el-descriptions-item>
      </el-descriptions>

      <div class="keys mt12">
        <el-text type="info" size="small">已配置字段：</el-text>
        <el-tag v-for="k in configuredKeys" :key="k" effect="plain" class="key-tag">{{ k }}</el-tag>
        <el-text v-if="!configuredKeys.length" type="info" size="small">尚未配置</el-text>
      </div>
    </el-card>

    <div class="mt16">
      <el-button type="primary" plain @click="goRun">前往执行页 →</el-button>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 820px;
}
.mt16 {
  margin-top: 16px;
}
.mb16 {
  margin-bottom: 16px;
}
.mt12 {
  margin-top: 12px;
}
.ph-title {
  font-weight: 600;
}
.card-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.keys {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.key-tag {
  font-family: ui-monospace, Consolas, monospace;
}
</style>
