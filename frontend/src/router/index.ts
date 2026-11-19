import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { runsRoutes } from '@/features/runs'
import AuthoringView from '@/features/authoring/AuthoringView.vue'
import ProjectsView from '@/features/authoring/ProjectsView.vue'
import RequirementsView from '@/features/authoring/RequirementsView.vue'
import CasesView from '@/features/authoring/CasesView.vue'
import { USE_MOCK } from '@/api/config'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/projects' },
  { path: '/projects', name: 'projects', component: ProjectsView },
  { path: '/projects/:projectId/requirements', name: 'requirements', component: USE_MOCK ? AuthoringView : RequirementsView, meta: { page: '需求管理' } },
  { path: '/projects/:projectId/cases', name: 'cases', component: USE_MOCK ? AuthoringView : CasesView, meta: { page: '测试用例' } },
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
