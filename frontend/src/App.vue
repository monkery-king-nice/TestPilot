<script setup lang="ts">
// 应用外壳：顶部导航 + 路由出口。最小可运行版本，由林彦羽扩充项目选择与 authoring 导航。
import { useRouter } from 'vue-router'

const router = useRouter()

function nav(path: string) {
  router.push(path)
}
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand" @click="nav('/')">
        <span class="logo">◈</span>
        <span class="name">TestPilot 智测领航</span>
      </div>
      <nav class="nav">
        <el-button text @click="nav('/projects/proj-demo-0001/environment')">环境配置</el-button>
        <el-button text @click="nav('/projects/proj-demo-0001/run')">执行测试</el-button>
      </nav>
    </header>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style>
:root {
  color-scheme: light;
}
body {
  margin: 0;
  background: #f5f6f8;
  color: #1f2329;
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
}
</style>

<style scoped>
.shell {
  min-height: 100vh;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 52px;
  background: #fff;
  border-bottom: 1px solid #e5e6eb;
  position: sticky;
  top: 0;
  z-index: 10;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.logo {
  color: #409eff;
  font-size: 20px;
}
.name {
  font-weight: 700;
  font-size: 15px;
}
.nav {
  display: flex;
  gap: 4px;
}
.content {
  padding: 20px 24px 40px;
}
</style>
