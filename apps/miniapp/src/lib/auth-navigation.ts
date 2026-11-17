import Taro from '@tarojs/taro'
import { authTabPaths, safeAuthTarget } from './auth-target'

const authPath = '/subpackages/account/auth/index'
const profilePath = '/subpackages/account/profile/index'
const profileOnboarding = `${profilePath}?onboarding=1`
type ProductIntent = { productId: string; skuId: string; quantity: number; action: 'cart' | 'buy' }
type AuthIntent = { target: string; source: string; phoneRequired: boolean; productExpires: number; product?: ProductIntent; resumeProfile?: boolean }
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
function activeIntent() {
  // Returning to a page must survive a long profile edit; only purchase choices expire.
  if (intent?.product && intent.productExpires <= Date.now()) intent.product = undefined
  return intent
}
export function authNeedsPhone() { return activeIntent()?.phoneRequired ?? true }
export async function beginAuthentication(target = currentAuthTarget(), phoneRequired = true, product?: ProductIntent) {
  const pages = Taro.getCurrentPages()
  if (opening || pages[pages.length - 1]?.route === authPath.slice(1)) return
  opening = true
  const previous = activeIntent()
  const page = pages[pages.length - 1]
  const resumeProfile = page?.route === profilePath.slice(1) && page.options?.onboarding === '1'
  const next: AuthIntent = resumeProfile
    ? { ...(previous ?? { target: '/pages/account/index', source: '/pages/account/index', productExpires: 0 }), phoneRequired, resumeProfile: true }
    : { target: safeAuthTarget(target) ?? '/pages/account/index', source: currentAuthTarget(), phoneRequired,
      productExpires: Date.now() + 15 * 60_000, product }
  intent = next
  try { await Taro.navigateTo({ url: authPath }) }
  catch (error) { if (intent === next) intent = previous; throw error }
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
export async function finishAuthentication({ fromProfile = false }: { fromProfile?: boolean } = {}) {
  const current = activeIntent()
  if (current?.resumeProfile && !fromProfile) {
    await go(profileOnboarding)
    if (intent === current) current.resumeProfile = false
    return
  }
  await go(current?.target ?? '/pages/account/index')
  if (intent === current && current) current.resumeProfile = false
  if (intent === current && !current?.product) intent = null
}
export async function cancelAuthentication() {
  const current = activeIntent()
  await go(current?.source ?? '/pages/home/index')
  if (intent === current) intent = null
}
export function consumeProductIntent(productId: string): ProductIntent | null {
  const current = activeIntent()
  if (current?.product?.productId !== productId) return null
  intent = null
  return current.product
}
