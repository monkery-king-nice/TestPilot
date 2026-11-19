// 执行页/结果页的纯展示逻辑（无框架依赖，Node 18+ 可直接测试）。
// 目标文案与运行前检查都从这里取，避免页面各写一套。

export function describeTarget(target) {
  if (!target) return '未冻结目标（旧批次）'
  const kind = target.kind === 'local' ? '本地服务' : '演示服务'
  const version = target.environment_version == null ? '' : ` · 环境 v${target.environment_version}`
  return `${kind} ${target.service_id}（${target.base_url}）${version}`
}

export function describeRequirementVersions(cases) {
  const versions = [...new Set((cases || []).map((c) => c.requirement_version).filter((v) => v != null))]
  if (versions.length === 0) return '—'
  return versions.map((v) => `v${v}`).join('、')
}

export function isEnvironmentConfigured(environment) {
  // 无登录的本地服务保存后 configured_keys 为空，但有 environment_version 即已配置。
  return Boolean(environment && environment.environment_version !== null)
}

export function preflightState({ projectId, confirmedCases, endpoints, environment }) {
  const missing = []
  if (!endpoints || endpoints.length === 0) {
    missing.push({
      key: 'endpoints',
      label: '缺少接口登记',
      path: `/projects/${projectId}/requirements`,
      hint: '在需求页登记测试接口后继续'
    })
  }
  if (!isEnvironmentConfigured(environment)) {
    missing.push({
      key: 'environment',
      label: '未配置测试环境',
      path: `/projects/${projectId}/environment`,
      hint: '选择并保存项目已启动的本地服务'
    })
  }
  if (!confirmedCases || confirmedCases.length === 0) {
    missing.push({
      key: 'cases',
      label: '没有已确认用例',
      path: `/projects/${projectId}/cases`,
      hint: '在用例页确认至少一条用例'
    })
  }
  return { ready: missing.length === 0, missing }
}
