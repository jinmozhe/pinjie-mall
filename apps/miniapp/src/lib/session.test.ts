import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ConsumerSessionRead } from '@pinjie/api-client'
import type * as ApiModule from './api'
import type { Envelope } from './api'

const mocks = vi.hoisted(() => ({ request: vi.fn(), upload: vi.fn(), storage: new Map<string, unknown>(), login: vi.fn(), privacy: vi.fn(), privacySetting: vi.fn(), cancel: vi.fn(), remove: vi.fn(), invalidate: vi.fn() }))
vi.mock('./upload', () => ({ uploadAvatar: mocks.upload }))
vi.mock('@tarojs/taro', () => ({ default: { login: mocks.login, requirePrivacyAuthorize: mocks.privacy, getPrivacySetting: mocks.privacySetting, setStorageSync: (key: string, value: unknown) => mocks.storage.set(key, value), getStorageSync: (key: string) => mocks.storage.get(key), removeTabBarBadge: () => Promise.resolve() } }))
vi.mock('./query', () => ({ queryClient: { cancelQueries: mocks.cancel, removeQueries: mocks.remove, invalidateQueries: mocks.invalidate } }))
vi.mock('./api', async () => { const actual = await vi.importActual<typeof ApiModule>('./api'); return { ...actual, request: mocks.request } })

function credentials(name = 'a'): ConsumerSessionRead {
  return { user: { id: name, display_name: null, avatar: null, phone_bound: false, phone_masked: null }, session_id: name, access_token: `access-${name}`, refresh_token: `refresh-${name}`, access_expires_at: new Date(Date.now() + 600_000).toISOString(), idle_expires_at: '2030-01-01T00:00:00Z', absolute_expires_at: '2030-01-01T00:00:00Z' }
}
describe('private session isolation', () => {
  beforeEach(() => { vi.resetModules(); vi.resetAllMocks(); mocks.storage.clear(); mocks.login.mockResolvedValue({ code: 'one-use' }); mocks.cancel.mockResolvedValue(undefined); mocks.invalidate.mockResolvedValue(undefined) })
  it('identifies a first visitor without privacy prompts or fabricated agreement', async () => {
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials())
    const session = await import('./session')
    await session.restoreSession()
    expect(session.signedIn()).toBe(true)
    expect(session.phoneReady()).toBe(false)
    expect(mocks.privacy).not.toHaveBeenCalled()
    expect(mocks.privacySetting).not.toHaveBeenCalled()
    expect(mocks.storage.has('pinjie.privacy-consent')).toBe(false)
    const identity = await session.login()
    expect(identity.user.id).toBe('a')
    expect(identity.epoch).toBe(session.sessionScope())
    expect(mocks.request.mock.calls.filter(([path]) => path === '/auth/login')).toHaveLength(1)
  })
  it('shares one identity request between startup and an explicit login', async () => {
    let resolve!: (value: unknown) => void
    mocks.request.mockImplementationOnce(() => new Promise((done) => { resolve = done })).mockResolvedValueOnce(credentials())
    const session = await import('./session')
    const startup = session.restoreSession()
    const first = session.login()
    const second = session.login()
    resolve({ login_enabled: true })
    const [, a, b] = await Promise.all([startup, first, second])
    expect(a).toEqual(b)
    expect(mocks.login).toHaveBeenCalledTimes(1)
    expect(mocks.request.mock.calls.filter(([path]) => path === '/auth/login')).toHaveLength(1)
  })
  it('rejects identity failures and permits an explicit fresh attempt', async () => {
    mocks.request.mockResolvedValueOnce({ login_enabled: false })
    const session = await import('./session')
    await expect(session.login()).rejects.toThrow('微信登录尚未开放')
    expect(session.signedIn()).toBe(false)
    expect(mocks.login).not.toHaveBeenCalled()
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockRejectedValueOnce(new Error('换码结果未确认'))
    await expect(session.login()).rejects.toThrow('换码结果未确认')
    expect(session.signedIn()).toBe(false)
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials())
    await expect(session.login()).resolves.toMatchObject({ user: { id: 'a' } })
  })
  it('binds the independent phone code to the same established account', async () => {
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials())
    const session = await import('./session')
    await session.restoreSession()
    const before = await session.login()
    mocks.request.mockResolvedValueOnce({ ...before.user, phone_bound: true, phone_masked: '138****2468' })
    await session.bindPhone('phone-once')
    const after = await session.login()
    expect(after.epoch).toBe(before.epoch)
    expect(after.user.id).toBe(before.user.id)
    expect(session.phoneReady()).toBe(true)
    expect(mocks.request).toHaveBeenLastCalledWith('/users/me/phone', expect.objectContaining({ method: 'POST', data: { code: 'phone-once' }, accessToken: 'access-a' }))
    expect(mocks.request.mock.calls.filter(([path]) => path === '/auth/login')).toHaveLength(1)
  })
  it('does not retry a phone code when binding fails', async () => {
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials())
    const session = await import('./session')
    await session.login()
    mocks.request.mockRejectedValueOnce(new Error('绑定结果未知'))
    await expect(session.bindPhone('phone-once')).rejects.toThrow('绑定结果未知')
    expect(session.phoneReady()).toBe(false)
    expect(mocks.request.mock.calls.filter(([path]) => path === '/users/me/phone')).toHaveLength(1)
  })
  it('does not exchange a late platform login code after logout', async () => {
    let resolve!: (value: { code: string }) => void
    mocks.request.mockResolvedValueOnce({ login_enabled: true })
    mocks.login.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const session = await import('./session')
    const pending = session.login()
    const rejected = expect(pending).rejects.toThrow('会话已改变')
    await vi.waitFor(() => expect(mocks.login).toHaveBeenCalledOnce())
    await session.logout()
    resolve({ code: 'late-code' })
    await rejected
    expect(session.signedIn()).toBe(false)
    expect(mocks.request.mock.calls.some(([path]) => path === '/auth/login')).toBe(false)
  })
  it('rejects an old exchange result without overwriting a newer login', async () => {
    let resolveOld!: (value: unknown) => void
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockImplementationOnce(() => new Promise((done) => { resolveOld = done }))
    const session = await import('./session')
    const old = session.login()
    const rejected = expect(old).rejects.toThrow('会话已改变')
    await vi.waitFor(() => expect(mocks.request.mock.calls.some(([path]) => path === '/auth/login')).toBe(true))
    await session.logout()
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials('current'))
    const current = await session.login()
    resolveOld(credentials('old'))
    await rejected
    expect(await session.login()).toEqual(current)
    expect(mocks.storage.get('pinjie.signed-out')).toBe(false)
  })
  it('blocks login while the current session is being revoked', async () => {
    mocks.request.mockResolvedValueOnce({ login_enabled: true }).mockResolvedValueOnce(credentials())
    const session = await import('./session')
    await session.login()
    let resolve!: (value: unknown) => void
    mocks.request.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const exiting = session.logout()
    await expect(session.login()).rejects.toThrow('正在退出')
    resolve(null)
    await exiting
    expect(session.signedIn()).toBe(false)
    const calls = mocks.request.mock.calls.length
    await session.restoreSession()
    expect(mocks.request).toHaveBeenCalledTimes(calls)
  })
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
    const pending = session.privateRequest<Envelope>('/users/me')
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
    expect(mocks.request.mock.calls.filter(([path]) => path === '/auth/refresh')).toHaveLength(1)
    expect(mocks.request.mock.calls.filter(([path]) => path === '/orders')).toHaveLength(1)
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
