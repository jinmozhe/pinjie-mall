const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const routes: Record<string, readonly string[]> = {
  '/pages/home/index': [], '/pages/category/index': [], '/pages/cart/index': [], '/pages/account/index': [],
  '/subpackages/catalog/detail/index': ['id'],
  '/subpackages/account/addresses/index': [], '/subpackages/account/profile/index': [],
  '/subpackages/account/settings/index': [], '/subpackages/account/sessions/index': [], '/subpackages/account/closure/index': [],
  '/subpackages/finance/membership/index': [], '/subpackages/finance/wallets/index': [],
  '/subpackages/finance/ledgers/index': ['type'], '/subpackages/finance/commissions/index': [],
  '/subpackages/finance/withdrawals/index': [], '/subpackages/finance/referral/index': ['invite'], '/subpackages/finance/points/index': [],
  '/subpackages/trade/checkout/index': [], '/subpackages/trade/orders/index': ['status', 'fulfillment'],
  '/subpackages/trade/order-detail/index': ['id'], '/subpackages/service/refund-apply/index': ['orderId'],
  '/subpackages/service/refunds/index': ['orderId'], '/subpackages/service/refund-detail/index': ['id'],
  '/subpackages/service/review/index': ['orderId', 'itemId'],
}

export function safeAuthTarget(url: string): string | null {
  if (url.length > 1024 || url.includes('#')) return null
  const [path, raw = '', extra] = url.split('?')
  const allowed = routes[path]
  if (!allowed || extra !== undefined) return null
  const parts: string[] = []
  const seen = new Set<string>()
  for (const item of raw ? raw.split('&') : []) {
    const [key, encoded, excess] = item.split('=')
    if (!allowed.includes(key) || seen.has(key) || encoded === undefined || excess !== undefined) return null
    let value: string
    try { value = decodeURIComponent(encoded) } catch { return null }
    if ((key === 'id' || key.endsWith('Id')) ? !uuid.test(value) : !/^[a-zA-Z0-9_-]{1,64}$/.test(value)) return null
    seen.add(key); parts.push(`${key}=${encodeURIComponent(value)}`)
  }
  return path + (parts.length ? `?${parts.join('&')}` : '')
}

export const authTabPaths = new Set(['/pages/home/index', '/pages/category/index', '/pages/cart/index', '/pages/account/index'])
