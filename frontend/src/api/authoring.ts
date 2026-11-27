import { apiFetch, projectPath } from './client'
import type { Case, CaseDraft } from './types'

export type Project = { id: string; name: string }
export type RequirementSource = { import_id: string; path: string; start: number; end: number }
export type Requirement = { id: string; text: string; version: number; source?: RequirementSource }
export type Endpoint = { id: string; method: string; path: string; version: number }
export type Clarification = {
  status: 'NEEDS_INFO' | 'READY'
  questions: { quote: string; question: string; source_path?: string }[]
  dropped?: number
}
export type ImportCandidate = {
  candidate_id: string; source_path: string; method: string; path: string; summary: string
  requires_manual_registration: boolean
  request_fields?: { name: string; type: string; required: boolean }[]
  parameters: { name: string; in: string; required: boolean; type?: string; description?: string }[]
  responses: { status: string; description: string }[]
}
export type ProjectImport = {
  id: string; project_id: string; filename: string
  documents: { path: string; size: number }[]
  endpoint_candidates: ImportCandidate[]; needs_manual_endpoints: boolean; warnings: string[]
  confirmed_endpoints: { candidate_id: string; endpoint: Endpoint }[]
}
export type DocumentPreview = RequirementSource & { text: string; total_chars: number }

const encode = encodeURIComponent
function write(method: 'POST' | 'PATCH', data: unknown) {
  return { method, body: JSON.stringify(data) }
}

export const listProjects = () => apiFetch<Project[]>('/api/projects')
export const createProject = (name: string) => apiFetch<Project>('/api/projects', write('POST', { name }))
export const listRequirements = (p: string) => apiFetch<Requirement[]>(projectPath(p, '/requirements'))
export const createRequirement = (p: string, text: string, source?: RequirementSource) =>
  apiFetch<Requirement>(projectPath(p, '/requirements'), write('POST', { text, source }))
export const updateRequirement = (p: string, id: string, text: string, expected_version?: number) =>
  apiFetch<Requirement>(projectPath(p, '/requirements/' + encode(id)), write('PATCH', { text, expected_version }))
export const listEndpoints = (p: string) => apiFetch<Endpoint[]>(projectPath(p, '/endpoints'))
export const createEndpoint = (p: string, method: string, path: string) =>
  apiFetch<Endpoint>(projectPath(p, '/endpoints'), write('POST', { method, path }))
export const previewModelInput = (p: string, requirement_id: string, requirement_version: number) =>
  apiFetch<{ context: unknown; digest: string }>(projectPath(p, "/agent/preview"), write("POST", { requirement_id, requirement_version }))
export const clarifyRequirement = (p: string, requirement_id: string, requirement_version: number, context_digest?: string) =>
  apiFetch<Clarification>(projectPath(p, '/agent/clarify'), write('POST', { requirement_id, requirement_version, context_digest }))
export type BasisReview = { source: "requirement" | "document" | "unverified"; exact: boolean; path?: string | null }
export const generateCases = (p: string, requirement_id: string, requirement_version: number, context_digest?: string) =>
  apiFetch<{ drafts: CaseDraft[]; reviews?: BasisReview[] }>(projectPath(p, '/agent/generate'), write('POST', { requirement_id, requirement_version, context_digest }))
export const saveCase = (p: string, draft: CaseDraft, id?: string) =>
  apiFetch<Case>(projectPath(p, id ? '/cases/' + encode(id) : '/cases'), write(id ? 'PATCH' : 'POST', draft))
export const confirmCase = (p: string, id: string, version: number) =>
  apiFetch<Case>(projectPath(p, '/cases/' + encode(id) + '/confirm'), write('POST', { version }))

export const uploadProject = (p: string, file: File) =>
  apiFetch<ProjectImport>(projectPath(p, '/imports?filename=' + encode(file.name)), {
    method: 'POST', headers: { 'Content-Type': 'application/zip' }, body: file,
  })
export const getProjectImport = (p: string, id: string) =>
  apiFetch<ProjectImport>(projectPath(p, '/imports/' + encode(id)))
export const previewDocument = (p: string, id: string, path: string, start = 0, end?: number) =>
  apiFetch<DocumentPreview>(projectPath(p, '/imports/' + encode(id) + '/preview'), write('POST', { path, start, end }))
export const confirmImportEndpoints = (p: string, id: string, candidate_ids: string[]) =>
  apiFetch<{ endpoints: ProjectImport['confirmed_endpoints'] }>(
    projectPath(p, '/imports/' + encode(id) + '/confirm-endpoints'), write('POST', { candidate_ids }),
  )
