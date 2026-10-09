import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { MiniappSessionRead } from '@pinjie/api-client'
import type * as ApiModule from './api'
import type { Envelope } from './api'

const mocks = vi.hoisted(() => ({ request: vi.fn(), upload: vi.fn(), storage: new Map<string, unknown>(), login: vi.fn(), cancel: vi.fn(), remove: vi.fn() }))
vi.mock('./upload', () => ({ uploadAvatar: mocks.upload }))
vi.mock('@tarojs/taro', () => ({ default: { login: mocks.login, setStorageSync: (key: string, value: unknown) => mocks.storage.set(key, value), getStorageSync: (key: string) => mocks.storage.get(key), removeTabBarBadge: () => Promise.resolve() } }))
vi.mock('./query', () => ({ queryClient: { cancelQueries: mocks.cancel, removeQueries: mocks.remove } }))
vi.mock('./api', async () => { const actual = await vi.importActual<typeof ApiModule>('./api'); return { ...actual, request: mocks.request } })

function credentials(name = 'a'): MiniappSessionRead {
  return { user: { id: name, display_name: null, avatar: null }, session_id: name, access_token: `access-${name}`, refresh_token: `refresh-${name}`, access_expires_at: new Date(Date.now() + 600_000).toISOString(), idle_expires_at: '2030-01-01T00:00:00Z', absolute_expires_at: '2030-01-01T00:00:00Z' }
}
describe('private session isolation', () => {
  beforeEach(() => { vi.resetModules(); mocks.request.mockReset(); mocks.upload.mockReset(); mocks.storage.clear(); mocks.login.mockResolvedValue({ code: 'one-use' }); mocks.cancel.mockResolvedValue(undefined) })
  it('never persists credentials and explicit logout blocks cold restoration', async () => {
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials()).mockResolvedValueOnce(null)
    const session = await import('./session')
    await session.login(); expect(session.signedIn()).toBe(true)
    expect([...mocks.storage.values()].every((value) => typeof value === 'boolean')).toBe(true)
    await session.logout(); expect(session.signedIn()).toBe(false)
    const calls = mocks.request.mock.calls.length
    await session.restoreSession(); expect(mocks.request).toHaveBeenCalledTimes(calls)
    expect(mocks.remove).toHaveBeenCalledWith({ queryKey: ['private'] })
  })
  it('does not refill a new session with an old private response', async () => {
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials())
    const session = await import('./session'); await session.login()
    let resolve!: (value: unknown) => void
    mocks.request.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const pending = session.privateRequest<Envelope>('/me')
    mocks.request.mockResolvedValueOnce(null)
    await session.logout(); resolve({ id: 'old' })
    await expect(pending).rejects.toThrow('会话已改变')
    expect(session.signedIn()).toBe(false)
  })
  it('rotates once before concurrent writes and does not replay them', async () => {
    const old = credentials(); old.access_expires_at = new Date(0).toISOString()
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(old)
    const session = await import('./session'); await session.login()
    mocks.request.mockResolvedValueOnce(credentials()).mockResolvedValue({ id: 'accepted' })
    await Promise.all([session.privateRequest<Envelope>('/orders', { method: 'POST' }), session.privateRequest<Envelope>('/cart-items', { method: 'POST' })])
    expect(mocks.request.mock.calls.filter(([path]) => path === '/miniapp/auth/refresh')).toHaveLength(1)
    expect(mocks.request.mock.calls.filter(([path]) => path === '/miniapp/orders')).toHaveLength(1)
  })
  it('cancels an old upload and rejects its late response after logout', async () => {
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials())
    const session = await import('./session'); await session.login()
    let resolve!: (value: unknown) => void
    mocks.upload.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const pending = session.privateAvatarUpload('/tmp/avatar.png')
    const signal = mocks.upload.mock.calls[0][2]
    mocks.request.mockResolvedValueOnce(null)
    await session.logout()
    expect(signal.aborted).toBe(true)
    resolve({ id: 'old', url: 'old' })
    await expect(pending).rejects.toThrow('会话已改变')
    expect(mocks.upload).toHaveBeenCalledTimes(1)
    expect(() => session.updateSessionUser(credentials().user, session.sessionScope() - 1)).toThrow()
  })
})
