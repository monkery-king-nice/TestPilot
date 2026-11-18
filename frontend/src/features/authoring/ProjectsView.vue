<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiFetch } from '@/api/client'
import { USE_MOCK } from '@/api/config'

type Project = { id: string; name: string }
const projects = ref<Project[]>([])
const error = ref('')
const loading = ref(false)

async function loadProjects() {
  loading.value = true
  error.value = ''
  try {
    projects.value = USE_MOCK
      ? [{ id: 'proj-demo-0001', name: '接口测试演示项目' }]
      : await apiFetch<Project[]>('/api/projects')
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法加载项目'
  } finally {
    loading.value = false
  }
}

onMounted(loadProjects)
</script>

<template>
  <section>
    <h1>选择项目</h1>
    <p v-if="loading" role="status">正在加载项目…</p>
    <template v-else-if="error">
      <el-alert :title="error" type="error" :closable="false" />
      <el-button @click="loadProjects">重试</el-button>
    </template>
    <p v-else-if="!projects.length">暂无项目</p>
    <ul v-else>
      <li v-for="project in projects" :key="project.id">
        <router-link :to="{ name: 'requirements', params: { projectId: project.id } }">
          {{ project.name }}
        </router-link>
      </li>
    </ul>
  </section>
</template>
