// 环境、执行与结果功能的路由定义。
// 交由前端负责人（林彦羽）在 router/index.ts 中注册，见本文件顶部的注册说明。

import type { RouteRecordRaw } from 'vue-router'
import EnvironmentView from './EnvironmentView.vue'
import RunListView from './RunListView.vue'
import RunDetailView from './RunDetailView.vue'

/** 路由名常量，供 router.push({ name }) 使用 */
export const RUNS_ROUTE_NAMES = {
  environment: 'runs-environment',
  list: 'runs-list',
  detail: 'runs-detail'
} as const

/**
 * 路由注册说明（给林彦羽）：
 * 1. 依赖项目上下文，均挂在 /projects/:projectId 下；projectId 由林彦羽的项目选择/入口提供。
 * 2. 三条路由：环境配置、执行列表、运行详情。执行列表发起运行后跳转到详情。
 * 3. 在 router/index.ts 中：import { runsRoutes } from '@/features/runs'; routes.push(...runsRoutes)。
 * 4. 详情页 /projects/:projectId/runs/:runId 通过刷新可恢复运行状态（useRunPolling.restore）。
 */
export const runsRoutes: RouteRecordRaw[] = [
  {
    path: '/projects/:projectId/environment',
    name: RUNS_ROUTE_NAMES.environment,
    component: EnvironmentView,
    meta: { title: '环境配置', feature: 'runs' }
  },
  {
    path: '/projects/:projectId/run',
    name: RUNS_ROUTE_NAMES.list,
    component: RunListView,
    meta: { title: '执行测试', feature: 'runs' }
  },
  {
    path: '/projects/:projectId/runs/:runId',
    name: RUNS_ROUTE_NAMES.detail,
    component: RunDetailView,
    meta: { title: '运行详情', feature: 'runs' }
  }
]
