import type { Analysis } from '@/api/types'

export interface AnalysisRequestStore {
  readonly analysis: Analysis | null
  readonly loading: boolean
  readonly error: string | null
  reset(key: string): void
  run(key: string, fetcher: () => Promise<Analysis>): Promise<void>
}

export function createAnalysisRequestStore(): AnalysisRequestStore
export function describeAnalysisError(error: unknown): string
