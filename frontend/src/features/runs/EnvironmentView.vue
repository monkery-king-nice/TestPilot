<script setup lang="ts">
// 环境页：选择执行目标（演示服务或项目已启动的本地服务），保存凭证后只显示字段名。
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { useEnvironment } from './composables/useEnvironment'
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
const isLocal = computed(() => form.target === 'local')

onMounted(async () => {
  await load()
  form.target = target.value
  form.serviceId = serviceId.value ?? ''
  form.baseUrl = baseUrl.value ?? ''
})

async function onSubmit() {
  if (isLocal.value && (!form.serviceId.trim() || !form.baseUrl.trim())) {
    ElMessage.warning('本地服务需要填写服务标识与回环地址')
    return
  }
  const hasCredentials = Boolean(form.username.trim() && form.password.trim())
  if (form.target === 'demo' && !hasCredentials) {
    ElMessage.warning('演示服务需要填写用户名和密码')
    return
  }
  // 本地服务可以没有登录：凭据留空时不发送 secrets，后端按无凭据环境保存。
  const secrets = hasCredentials ? { username: form.username, password: form.password } : undefined
  const write =
    form.target === 'local'
      ? {
          target: 'local' as const,
          service_id: form.serviceId.trim(),
          base_url: form.baseUrl.trim(),
          secrets
        }
      : { target: 'demo' as const, secrets: secrets! }
  await save(write)
  form.password = ''
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
        </template>

        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="被测服务的登录账号（如需要）" style="max-width: 320px" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            :type="showPassword ? 'text' : 'password'"
            placeholder="被测服务的登录密码（如需要）"
            style="max-width: 320px"
          >
            <template #append>
              <el-button @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</el-button>
            </template>
          </el-input>
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
