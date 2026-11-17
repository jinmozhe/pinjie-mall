import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  pages: [] as { route: string; options?: Record<string, string> }[],
  navigateTo: vi.fn(), navigateBack: vi.fn(), redirectTo: vi.fn(), switchTab: vi.fn(),
}))
vi.mock('@tarojs/taro', () => ({ default: {
  getCurrentPages: () => mocks.pages,
  navigateTo: mocks.navigateTo, navigateBack: mocks.navigateBack, redirectTo: mocks.redirectTo, switchTab: mocks.switchTab,
} }))
const profile = { route: 'subpackages/account/profile/index', options: { onboarding: '1' } }
const login = { route: 'subpackages/account/auth/index' }
const order = { route: 'subpackages/trade/orders/index', options: { status: 'pending_payment', fulfillment: 'physical' } }
const orderUrl = '/subpackages/trade/orders/index?status=pending_payment&fulfillment=physical'

describe('authentication and first phone binding return navigation', () => {
  beforeEach(() => {
    vi.resetModules(); vi.resetAllMocks()
    mocks.pages = [order]
    mocks.navigateTo.mockResolvedValue(undefined); mocks.navigateBack.mockResolvedValue(undefined)
    mocks.redirectTo.mockResolvedValue(undefined); mocks.switchTab.mockResolvedValue(undefined)
  })
  afterEach(() => vi.restoreAllMocks())

  it('returns from profile to the original page stack with its filters', async () => {
    const nav = await import('./auth-navigation')
    await nav.beginAuthentication()
    expect(nav.currentAuthTarget()).toBe(orderUrl)
    expect(mocks.navigateTo).toHaveBeenCalledWith({ url: `/${login.route}` })
    mocks.pages = [order, profile]
    await nav.finishAuthentication({ fromProfile: true })
    expect(mocks.navigateBack).toHaveBeenCalledTimes(1)
    expect(mocks.redirectTo).not.toHaveBeenCalled()
  })

  it('keeps an explicit private destination through a long profile edit', async () => {
    const nav = await import('./auth-navigation')
    const now = vi.spyOn(Date, 'now').mockReturnValue(1000)
    mocks.pages = [{ route: 'pages/account/index' }]
    await nav.beginAuthentication(orderUrl)
    mocks.pages.push(profile)
    now.mockReturnValue(3_601_000)
    await nav.finishAuthentication({ fromProfile: true })
    expect(mocks.redirectTo).toHaveBeenCalledWith({ url: orderUrl })
    await nav.finishAuthentication()
    expect(mocks.switchTab).toHaveBeenCalledWith({ url: '/pages/account/index' })
  })

  it('resumes profile after reauthentication without replacing the original target', async () => {
    const nav = await import('./auth-navigation')
    await nav.beginAuthentication()
    mocks.pages = [order, profile]
    await nav.beginAuthentication(undefined, false)
    expect(nav.authNeedsPhone()).toBe(false)
    mocks.pages.push(login)
    await nav.finishAuthentication()
    expect(mocks.navigateBack).toHaveBeenCalledTimes(1)
    mocks.pages.pop()
    await nav.finishAuthentication({ fromProfile: true })
    expect(mocks.navigateBack).toHaveBeenCalledTimes(2)
  })

  it('can skip profile after native back from reauthentication', async () => {
    const nav = await import('./auth-navigation')
    await nav.beginAuthentication()
    mocks.pages = [order, profile]
    await nav.beginAuthentication(undefined, false)
    await nav.finishAuthentication({ fromProfile: true })
    expect(mocks.navigateBack).toHaveBeenCalledTimes(1)
    expect(mocks.redirectTo).not.toHaveBeenCalled()
  })

  it('retains the target when return navigation fails, then clears after success', async () => {
    const nav = await import('./auth-navigation')
    await nav.beginAuthentication()
    mocks.pages = [profile]
    mocks.redirectTo.mockRejectedValueOnce(new Error('route failure'))
    await expect(nav.finishAuthentication({ fromProfile: true })).rejects.toThrow('route failure')
    await nav.finishAuthentication({ fromProfile: true })
    expect(mocks.redirectTo).toHaveBeenLastCalledWith({ url: orderUrl })
    await nav.finishAuthentication()
    expect(mocks.switchTab).toHaveBeenCalledWith({ url: '/pages/account/index' })
  })

  it('returns cancellation to the source, retaining it on navigation failure', async () => {
    const nav = await import('./auth-navigation')
    await nav.beginAuthentication('/subpackages/finance/wallets/index')
    mocks.pages = [login]
    mocks.redirectTo.mockRejectedValueOnce(new Error('route failure'))
    await expect(nav.cancelAuthentication()).rejects.toThrow('route failure')
    await nav.cancelAuthentication()
    expect(mocks.redirectTo).toHaveBeenLastCalledWith({ url: orderUrl })
  })

  it('expires product choices after fifteen minutes without losing the product URL', async () => {
    const nav = await import('./auth-navigation')
    const now = vi.spyOn(Date, 'now').mockReturnValue(1000)
    const id = '01900000-0000-7000-8000-000000000001'
    const target = `/subpackages/catalog/detail/index?id=${id}`
    await nav.beginAuthentication(target, true, { productId: id, skuId: 'sku', quantity: 2, action: 'buy' })
    mocks.pages = [profile]
    now.mockReturnValue(901_000)
    await nav.finishAuthentication({ fromProfile: true })
    expect(mocks.redirectTo).toHaveBeenCalledWith({ url: target })
    expect(nav.consumeProductIntent(id)).toBeNull()
  })

  it('keeps fresh product choices for explicit confirmation and clears on logout', async () => {
    const nav = await import('./auth-navigation')
    const id = '01900000-0000-7000-8000-000000000001'
    const product = { productId: id, skuId: 'sku', quantity: 2, action: 'cart' as const }
    await nav.beginAuthentication(`/subpackages/catalog/detail/index?id=${id}`, true, product)
    mocks.pages = [profile]
    await nav.finishAuthentication({ fromProfile: true })
    expect(nav.consumeProductIntent(id)).toEqual(product)
    expect(nav.consumeProductIntent(id)).toBeNull()
    await nav.beginAuthentication(orderUrl)
    nav.clearAuthIntent()
    await nav.finishAuthentication()
    expect(mocks.switchTab).toHaveBeenLastCalledWith({ url: '/pages/account/index' })
  })

  it('does not erase a newer authentication started during an older return', async () => {
    const nav = await import('./auth-navigation')
    await nav.beginAuthentication()
    mocks.pages = [{ route: 'pages/account/index' }]
    let complete!: () => void
    mocks.redirectTo.mockImplementationOnce(() => new Promise<void>((resolve) => { complete = resolve }))
    const finishing = nav.finishAuthentication()
    await nav.beginAuthentication('/subpackages/finance/wallets/index')
    complete(); await finishing
    await nav.finishAuthentication()
    expect(mocks.redirectTo).toHaveBeenLastCalledWith({ url: '/subpackages/finance/wallets/index' })
  })
})
