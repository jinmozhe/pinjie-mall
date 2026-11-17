import { describe, expect, it } from 'vitest'
import { safeAuthTarget } from './auth-target'

describe('authentication return target', () => {
  it('preserves legitimate private filters and product identifiers', () => {
    const product = '/subpackages/catalog/detail/index?id=01900000-0000-7000-8000-000000000001'
    expect(safeAuthTarget(product)).toBe(product)
    expect(safeAuthTarget('/subpackages/trade/orders/index?status=pending_payment')).toBe('/subpackages/trade/orders/index?status=pending_payment')
    expect(safeAuthTarget('/subpackages/account/profile/index?onboarding=1')).toBe('/subpackages/account/profile/index?onboarding=1')
  })
  it.each(['https://example.com', '/subpackages/account/auth/index', '/pages/account/index?token=secret',
    '/subpackages/trade/orders/index?status=a&status=b', '/subpackages/trade/order-detail/index?id=not-a-uuid',
    '/pages/home/index#secret', '/subpackages/trade/orders/index?status=%ZZ',
    '/subpackages/account/profile/index?onboarding=2'])('rejects unsafe return %s', (url) => {
    expect(safeAuthTarget(url)).toBeNull()
  })
})
