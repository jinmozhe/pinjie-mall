import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearRevocation, loadRevocation, saveRevocation } from './intent'

const storage = vi.hoisted(() => new Map<string, unknown>())
vi.mock('@tarojs/taro', () => ({ default: {
  getStorageSync: (key: string) => storage.get(key),
  setStorageSync: vi.fn((key: string, value: unknown) => { storage.set(key, value) }),
  removeStorageSync: (key: string) => storage.delete(key),
} }))
const target = { session_ids: ['01990000-0000-7000-8000-000000000001'] }
describe('owner-scoped revocation recovery', () => {
  beforeEach(() => storage.clear())
  it('preserves original ids across reload without exposing another account intent', () => {
    saveRevocation({ version: 1, userId: 'owner', target })
    expect(loadRevocation('owner')?.target).toEqual(target)
    expect(loadRevocation('other')).toBeNull()
    clearRevocation('other'); expect(loadRevocation('owner')).not.toBeNull()
    clearRevocation('owner'); expect(loadRevocation('owner')).toBeNull()
  })
  it('fails closed for corrupt or cross-account data', () => {
    storage.set('pinjie.session-revocation.owner', false)
    expect(() => loadRevocation('owner')).toThrow('无效')
    storage.set('pinjie.session-revocation.owner', { version: 1, userId: 'other', target })
    expect(() => loadRevocation('owner')).toThrow('无效')
    storage.set('pinjie.session-revocation.owner', { version: 1, userId: 'owner', target: { session_ids: [target.session_ids[0], target.session_ids[0]] } })
    expect(() => loadRevocation('owner')).toThrow('无效')
  })
})
