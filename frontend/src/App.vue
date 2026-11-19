<script setup lang="ts">
import { useRoute } from 'vue-router'
import { USE_MOCK } from '@/api/config'

const route = useRoute()
const nav = [
  { name: 'requirements', title: '需求管理' },
  { name: 'cases', title: '测试用例' },
  { name: 'runs-environment', title: '环境配置' },
  { name: 'runs-list', title: '执行与结果' },
]
</script>

<template>
  <header class="app-nav">
    <strong>智测领航</strong>
    <router-link :to="{ name: 'projects' }">项目列表</router-link>
    <template v-if="route.params.projectId">
      <router-link v-for="item in nav" :key="item.name"
        :to="{ name: item.name, params: { projectId: route.params.projectId } }">
        {{ item.title }}
      </router-link>
    </template>
    <span v-if="USE_MOCK">样例模式</span>
  </header>
  <main class="app-content">
    <router-view v-slot="{ Component }">
      <component :is="Component" :key="String(route.params.projectId ?? '')" />
    </router-view>
  </main>
</template>

<style>
body { margin: 0; color: #202630; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; }
.app-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px; padding: 14px 20px; border-bottom: 1px solid #e2e6ed; }
.app-nav a { color: #2455cf; }
.app-nav .router-link-exact-active { font-weight: 700; }
.app-content { padding: 16px; }
</style>
