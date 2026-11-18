<script setup lang="ts">
// 环境页：配置演示服务凭证，保存后仅显示已配置的字段名（值只给服务端执行器）。
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useEnvironment } from './composables/useEnvironment'

const route = useRoute()
const router = useRouter()
const projectId = () => String(route.params.projectId)

const { target, configuredKeys, loading, saving, load, save } = useEnvironment(projectId)

const form = reactive({ username: '', password: '' })
const showPassword = ref(false)

onMounted(load)

async function onSubmit() {
  await save({ username: form.username, password: form.password })
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
          <span>演示凭证</span>
          <el-tag type="info" effect="plain">目标：{{ target }}</el-tag>
        </div>
      </template>

      <el-alert
        title="凭证值保存后不返回前端，仅服务端执行器可读取；此处只展示已配置的字段名。"
        type="info"
        :closable="false"
        class="mb16"
      />

      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="demo 账号，例如 demo" style="max-width: 320px" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            :type="showPassword ? 'text' : 'password'"
            placeholder="demo 密码"
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

    <el-card class="mt16" shadow="never" :body-style="{ padding: '20px' }">
      <template #header>
        <div class="card-h">
          <span>已配置字段（只展示字段名）</span>
          <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        </div>
      </template>

      <div v-if="configuredKeys.length" class="keys">
        <el-tag v-for="k in configuredKeys" :key="k" effect="plain" class="key-tag">{{ k }}</el-tag>
      </div>
      <el-empty v-else description="尚未配置任何字段" :image-size="60" />
    </el-card>

    <div class="mt16">
      <el-button type="primary" plain @click="goRun">前往执行页 →</el-button>
    </div>
  </div>
</template>

<style scoped>
.page {
  max-width: 760px;
}
.mt16 {
  margin-top: 16px;
}
.mb16 {
  margin-bottom: 16px;
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
}
.key-tag {
  font-family: ui-monospace, Consolas, monospace;
}
</style>
