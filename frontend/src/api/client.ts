// 极简 fetch 封装：统一错误结构 {"detail":"..."} 与 JSON 解析。
// 前端通过 /api 访问，Vite 开发代理指向 127.0.0.1:8000。

import type { ApiError } from './types'

export class HttpError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'HttpError'
    this.status = status
    this.detail = detail
  }
}

async function parseError(res: Response): Promise<HttpError> {
  let detail = res.statusText || `HTTP ${res.status}`
  try {
    const body = (await res.json()) as ApiError
    if (body && typeof body.detail === 'string') detail = body.detail
  } catch {
    // 非 JSON 响应体：保留状态文案
  }
  return new HttpError(res.status, detail)
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init
  })
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/**
 * 按文本读取响应（例如 `text/html` 报告），不做 JSON 解析。
 * 报告接口返回 HTML，用 apiFetch 的 res.json() 会解析失败。
 */
export async function apiFetchText(path: string, init?: RequestInit): Promise<string> {
  const res = await fetch(path, init)
  if (!res.ok) throw await parseError(res)
  return await res.text()
}

/** 拼接项目路径：P = /api/projects/{project_id} */
export function projectPath(projectId: string, suffix = ''): string {
  return `/api/projects/${encodeURIComponent(projectId)}${suffix}`
}
