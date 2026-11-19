import { apiFetch, projectPath } from './client'
import type { Case, CaseDraft } from './types'

export type Project = { id: string; name: string }
export type Requirement = { id: string; text: string; version: number }
export type Endpoint = { id: string; method: string; path: string; version: number }
export type Clarification = {
  status: 'NEEDS_INFO' | 'READY'
  questions: { quote: string; question: string }[]
}

const encode = encodeURIComponent
function write(method: 'POST' | 'PATCH', data: unknown) {
  return { method, body: JSON.stringify(data) }
}

export const listProjects = () => apiFetch<Project[]>('/api/projects')
export const createProject = (name: string) => apiFetch<Project>('/api/projects', write('POST', { name }))
export const listRequirements = (p: string) => apiFetch<Requirement[]>(projectPath(p, '/requirements'))
export const createRequirement = (p: string, text: string) =>
  apiFetch<Requirement>(projectPath(p, '/requirements'), write('POST', { text }))
export const updateRequirement = (p: string, id: string, text: string) =>
  apiFetch<Requirement>(projectPath(p, '/requirements/' + encode(id)), write('PATCH', { text }))
export const listEndpoints = (p: string) => apiFetch<Endpoint[]>(projectPath(p, '/endpoints'))
export const createEndpoint = (p: string, method: string, path: string) =>
  apiFetch<Endpoint>(projectPath(p, '/endpoints'), write('POST', { method, path }))
export const clarifyRequirement = (p: string, requirement_id: string) =>
  apiFetch<Clarification>(projectPath(p, '/agent/clarify'), write('POST', { requirement_id }))
export const generateCases = (p: string, requirement_id: string) =>
  apiFetch<{ drafts: CaseDraft[] }>(projectPath(p, '/agent/generate'), write('POST', { requirement_id }))
export const saveCase = (p: string, draft: CaseDraft, id?: string) =>
  apiFetch<Case>(projectPath(p, id ? '/cases/' + encode(id) : '/cases'), write(id ? 'PATCH' : 'POST', draft))
export const confirmCase = (p: string, id: string, version: number) =>
  apiFetch<Case>(projectPath(p, '/cases/' + encode(id) + '/confirm'), write('POST', { version }))
