import type { PaymentAttemptRead } from '@pinjie/api-client'

export function canInvokePayment(attempt: PaymentAttemptRead | null | undefined): boolean {
  return attempt?.status === 'pending' && !!attempt.payment_parameters
}

export function shouldPollPayment(status: string | undefined, visible: boolean, deadline: number, now: number): boolean {
  return visible && now < deadline && ['created', 'pending', 'unknown', 'succeeded'].includes(status ?? '')
}

export function isPaymentRequestId(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
}
