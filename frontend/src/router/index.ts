// 应用路由（最小可运行外壳）。
// 说明：项目选择与 authoring 路由由前端负责人（林彦羽）负责；
// 这里仅注册陈睿涛的 runs 功能路由，并提供一个演示项目入口方便独立演示。
// 正式联调时，林彦羽可将「项目选择」替换为真实项目列表，并补充 authoring 路由。
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { runsRoutes } from '@/features/runs'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/projects/proj-demo-0001/run'
  },
  // 项目选择入口：林彦羽负责实现真正的项目列表页。
  {
    path: '/projects',
    redirect: '/projects/proj-demo-0001/run'
  },
  ...runsRoutes,
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

export default router
