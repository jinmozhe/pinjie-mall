import { describe, expect, it } from 'vitest'
import type { PaymentAttemptRead } from '@pinjie/api-client'
import { canInvokePayment, isPaymentRequestId, shouldPollPayment } from './payment-domain'

describe('payment recovery boundaries', () => {
  const attempt: PaymentAttemptRead = {
    id: 'id', order_id: 'order', channel: 'wechat', merchant_reference: 'reference',
    status: 'pending', amount: '10.00', currency: 'CNY', unavailable_reason: null,
    created_at: '2026-11-18T00:00:00Z',
    payment_parameters: { timeStamp: '1', nonceStr: 'nonce', package: 'prepay_id=id', signType: 'RSA', paySign: 'signature' },
  }
  it.each(['created', 'unknown', 'succeeded', 'closed', 'unavailable'])('never invokes cashier for %s', (status) => {
    expect(canInvokePayment({ ...attempt, status })).toBe(false)
  })
  it('requires a confirmed prepay session', () => {
    expect(canInvokePayment(attempt)).toBe(true)
    expect(canInvokePayment({ ...attempt, payment_parameters: null })).toBe(false)
  })
  it('stops polling while hidden or after the deadline', () => {
    expect(shouldPollPayment('unknown', true, 60000, 1)).toBe(true)
    expect(shouldPollPayment('unknown', false, 60000, 1)).toBe(false)
    expect(shouldPollPayment('unknown', true, 60000, 60000)).toBe(false)
    expect(shouldPollPayment('closed', true, 60000, 1)).toBe(false)
    expect(shouldPollPayment('succeeded', true, 60000, 1)).toBe(true)
  })
  it('rejects corrupted stored request identifiers', () => {
    expect(isPaymentRequestId('01900000-0000-7000-8000-000000000001')).toBe(true)
    expect(isPaymentRequestId('-'.repeat(36))).toBe(false)
    expect(isPaymentRequestId({ request_id: 'id' })).toBe(false)
  })
})
