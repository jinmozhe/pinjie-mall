import Taro from '@tarojs/taro'
import type { CheckoutLine, CheckoutRequest, ResponseModelMiniappCheckoutIntentRead, ResponseModelMiniappUserRead } from '@pinjie/api-client'
import { privateRequest, sessionScope } from '@/lib/session'

export type Draft = { schemaVersion: 1; userId: string; productType: 'physical' | 'virtual'; request: CheckoutRequest; submitted: boolean }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
function key(userId: string) { return `pinjie.checkout.${userId}` }
export function loadDraft(userId: string): Draft | null {
  const value: unknown = Taro.getStorageSync(key(userId))
  if (!value) return null
  if (typeof value !== 'object' || !('userId' in value) || value.userId !== userId || !('request' in value) || !('submitted' in value) || typeof value.submitted !== 'boolean') throw new Error('结算记录格式无效，请联系支持，勿重复下单')
  if (!('schemaVersion' in value) || value.schemaVersion !== 1 || !('productType' in value) || !['physical', 'virtual'].includes(String(value.productType))) throw new Error('结算记录版本无效，请先核对订单结果')
  const draft = value as Draft
  if (!draft.request || !UUID.test(draft.request.request_id) || !Array.isArray(draft.request.items) || !draft.request.items.length || draft.request.items.length > 50 || draft.request.items.some((item) => !item || !UUID.test(item.sku_id) || !Number.isInteger(item.quantity) || item.quantity < 1 || item.quantity > 999) || draft.request.address_id != null && !UUID.test(draft.request.address_id) || draft.request.quote_fingerprint != null && !/^[0-9a-f]{64}$/.test(draft.request.quote_fingerprint) || draft.submitted && !draft.request.quote_fingerprint) throw new Error('结算记录格式无效，请联系支持，勿重复下单')
  return draft
}
export function saveDraft(draft: Draft) { Taro.setStorageSync(key(draft.userId), draft) }
export function removeDraft(userId: string) { Taro.removeStorageSync(key(userId)) }
export async function startCheckout(items: CheckoutLine[], productType: 'physical' | 'virtual') {
  if (!items.length || items.length > 50) throw new Error('请选择 1 至 50 种商品')
  const epoch = sessionScope()
  // The user id is read from the authenticated server, never from a caller-supplied identity.
  const me = await privateRequest<ResponseModelMiniappUserRead>('/me')
  const old = loadDraft(me.id)
  if (old?.submitted) { await Taro.navigateTo({ url: '/subpackages/trade/checkout/index' }); return }
  const intent = await privateRequest<ResponseModelMiniappCheckoutIntentRead>('/checkout/intent')
  if (epoch !== sessionScope()) throw new Error('登录状态已改变，请重新选择商品')
  saveDraft({ schemaVersion: 1, userId: me.id, productType, request: { request_id: intent.request_id, items }, submitted: false })
  await Taro.navigateTo({ url: '/subpackages/trade/checkout/index' })
}
