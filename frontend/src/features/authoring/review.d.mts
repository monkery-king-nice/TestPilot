import type { BasisReview } from '@/api/authoring'
import type { Assertion } from '@/api/types'
export function reviewLabel(review?: BasisReview): string
export function inputShape(body: unknown): string
export function assertionLabel(a: Assertion): string
