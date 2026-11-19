<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects, createProject, type Project } from '@/api/authoring'
import { USE_MOCK } from '@/api/config'

const router = useRouter()
const projects = ref<Project[]>([])
const error = ref('')
const loading = ref(false)
const projectName = ref('')
const creating = ref(false)

async function addProject() {
  if (!projectName.value.trim() || creating.value) return
  creating.value = true
  error.value = ''
  try {
    const project = await createProject(projectName.value.trim())
    await router.push({ name: 'requirements', params: { projectId: project.id } })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '无法创建项目'
  } finally {
    creating.value = false
  }
}

async function loadProjects() {
  loading.value = true
  error.value = ''
  try {
    projects.value = USE_MOCK
      ? [{ id: 'proj-demo-0001', name: '接口测试演示项目' }]
      : await listProjects()
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
    <form v-if="!USE_MOCK" class="create-project" @submit.prevent="addProject">
      <el-input v-model="projectName" maxlength="100" placeholder="项目名称" aria-label="项目名称" />
      <el-button type="primary" native-type="submit" :loading="creating" :disabled="!projectName.trim()">新建项目</el-button>
    </form>
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

<style scoped>
.create-project { display: flex; gap: 12px; max-width: 460px; margin-bottom: 18px; }
</style>
