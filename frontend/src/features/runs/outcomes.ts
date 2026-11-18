// 结果类型的展示元数据（颜色、文案），供统计卡片、标签等复用。
import type { Outcome } from '@/api/types'

export interface OutcomeMeta {
  label: string
  color: string
  bg: string
}

export const OUTCOME_META: Record<Outcome, OutcomeMeta> = {
  PASS: { label: '通过', color: '#16a34a', bg: '#f0fdf4' },
  FAIL: { label: '失败', color: '#dc2626', bg: '#fef2f2' },
  ERROR: { label: '错误', color: '#ea580c', bg: '#fff7ed' },
  BLOCKED: { label: '阻断', color: '#6b7280', bg: '#f9fafb' }
}

export const OUTCOME_ORDER: Outcome[] = ['PASS', 'FAIL', 'ERROR', 'BLOCKED']

export function outcomeMeta(outcome: Outcome): OutcomeMeta {
  return OUTCOME_META[outcome] ?? OUTCOME_META.BLOCKED
}
