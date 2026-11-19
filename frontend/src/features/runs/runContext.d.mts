import type { Case, EnvironmentRead, RunTarget } from '@/api/types'

export interface PreflightMissing {
  key: 'endpoints' | 'environment' | 'cases'
  label: string
  path: string
  hint: string
}

export function describeTarget(target: RunTarget | null): string
export function describeRequirementVersions(cases: Case[]): string
export function isEnvironmentConfigured(environment: EnvironmentRead | null): boolean
export function preflightState(input: {
  projectId: string
  confirmedCases: Case[]
  endpoints: unknown[]
  environment: EnvironmentRead | null
}): { ready: boolean; missing: PreflightMissing[] }
