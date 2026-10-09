import { beforeEach, describe, expect, it, vi } from 'vitest'
import Taro from '@tarojs/taro'
import { clearIntent, loadIntent, saveIntent } from './intent'
import type { RefundIntent } from './intent'

const storage = vi.hoisted(() => new Map<string, unknown>())
vi.mock('@tarojs/taro', () => ({ default: {
  getStorageSync: vi.fn((key: string) => storage.get(key)),
  setStorageSync: vi.fn((key: string, value: unknown) => { storage.set(key, value) }),
  removeStorageSync: vi.fn((key: string) => { storage.delete(key) }),
} }))

const original: RefundIntent = {
  version: 1,
  userId: '019a0000-0000-7000-8000-000000000001',
  orderId: '019a0000-0000-7000-8000-000000000002',
  request: { request_id: '019a0000-0000-7000-8000-000000000003', reason: '整单商品不再需要' },
}
beforeEach(() => { storage.clear(); vi.clearAllMocks() })

describe('unknown refund intent recovery', () => {
  it('retains the original request and isolates another user and order', () => {
    saveIntent(original)
    expect(loadIntent(original.userId, original.orderId)).toEqual(original)
    expect(loadIntent('019a0000-0000-7000-8000-000000000004', original.orderId)).toBeNull()
    expect(loadIntent(original.userId, '019a0000-0000-7000-8000-000000000005')).toBeNull()
    expect(loadIntent(original.userId, original.orderId)?.request).toEqual(original.request)
  })
  it('refuses corrupted or mismatched ownership instead of replacing the request', () => {
    storage.set(`pinjie.refund.${original.userId}.${original.orderId}`, { ...original, userId: 'other-user' })
    expect(() => loadIntent(original.userId, original.orderId)).toThrow()
    storage.set(`pinjie.refund.${original.userId}.${original.orderId}`, { ...original, request: { request_id: 'broken', reason: original.request.reason } })
    expect(() => loadIntent(original.userId, original.orderId)).toThrow()
  })
  it('propagates persistence failure so the caller can stop before sending a write', () => {
    vi.mocked(Taro.setStorageSync).mockImplementationOnce(() => { throw new Error('storage unavailable') })
    expect(() => saveIntent(original)).toThrow('storage unavailable')
    expect(loadIntent(original.userId, original.orderId)).toBeNull()
  })
  it('clears only the confirmed user and order record', () => {
    saveIntent(original)
    const another = { ...original, orderId: '019a0000-0000-7000-8000-000000000005' }
    saveIntent(another)
    clearIntent(original.userId, original.orderId)
    expect(loadIntent(original.userId, original.orderId)).toBeNull()
    expect(loadIntent(another.userId, another.orderId)).toEqual(another)
  })
})
