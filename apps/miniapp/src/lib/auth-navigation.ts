import Taro from '@tarojs/taro'
import { authTabPaths, safeAuthTarget } from './auth-target'

const authPath = '/subpackages/account/auth/index'
type ProductIntent = { productId: string; skuId: string; quantity: number; action: 'cart' | 'buy' }
type AuthIntent = { target: string; source: string; phoneRequired: boolean; expires: number; product?: ProductIntent }
let intent: AuthIntent | null = null
let opening = false

export function currentAuthTarget(offset = 0): string {
  const pages = Taro.getCurrentPages()
  const page = pages[pages.length - 1 - offset]
  if (!page) return '/pages/account/index'
  const query = Object.entries(page.options ?? {}).map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`).join('&')
  return safeAuthTarget(`/${page.route}${query ? `?${query}` : ''}`) ?? '/pages/account/index'
}
export function clearAuthIntent() { intent = null }
function activeIntent() { if (intent && intent.expires <= Date.now()) intent = null; return intent }
export function authNeedsPhone() { return activeIntent()?.phoneRequired ?? true }
export async function beginAuthentication(target = currentAuthTarget(), phoneRequired = true, product?: ProductIntent) {
  const pages = Taro.getCurrentPages()
  if (opening || pages[pages.length - 1]?.route === authPath.slice(1)) return
  opening = true
  intent = { target: safeAuthTarget(target) ?? '/pages/account/index', source: currentAuthTarget(), phoneRequired,
    expires: Date.now() + 15 * 60_000, product }
  try { await Taro.navigateTo({ url: authPath }) }
  catch (error) { intent = null; throw error }
  finally { opening = false }
}
async function go(target: string) {
  const pages = Taro.getCurrentPages()
  const previous = pages[pages.length - 2]
  if (previous && currentAuthTarget(1) === target) { await Taro.navigateBack(); return }
  const path = target.split('?')[0]
  if (authTabPaths.has(path)) await Taro.switchTab({ url: path })
  else await Taro.redirectTo({ url: target })
}
export async function finishAuthentication() {
  const current = activeIntent()
  await go(current?.target ?? '/pages/account/index')
  if (!current?.product) intent = null
}
export async function cancelAuthentication() {
  const current = activeIntent()
  intent = null
  await go(current?.source ?? '/pages/home/index')
}
export function consumeProductIntent(productId: string): ProductIntent | null {
  const current = activeIntent()
  if (current?.product?.productId !== productId) return null
  intent = null
  return current.product
}
export function profileGuideKey(userId: string) { return `pinjie.profile-guide.v1.${userId}` }
