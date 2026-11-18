import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { runsRoutes } from '@/features/runs'
import AuthoringView from '@/features/authoring/AuthoringView.vue'
import ProjectsView from '@/features/authoring/ProjectsView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/projects' },
  { path: '/projects', name: 'projects', component: ProjectsView },
  { path: '/projects/:projectId/requirements', name: 'requirements', component: AuthoringView, meta: { page: '需求管理' } },
  { path: '/projects/:projectId/cases', name: 'cases', component: AuthoringView, meta: { page: '测试用例' } },
  ...runsRoutes,
  {
    path: '/:pathMatch(.*)*',
    redirect: '/'
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
