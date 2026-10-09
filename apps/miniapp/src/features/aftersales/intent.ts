import Taro from '@tarojs/taro'
import type { RefundRequestCreate } from '@pinjie/api-client'

export type RefundIntent = { version: 1; userId: string; orderId: string; request: RefundRequestCreate }
export const validId = (value: string | undefined): value is string => !!value && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
const key = (userId: string, orderId: string) => `pinjie.refund.${userId}.${orderId}`
export function loadIntent(userId: string, orderId: string): RefundIntent | null {
  const value: unknown = Taro.getStorageSync(key(userId, orderId))
  if (!value) return null
  if (typeof value !== 'object' || !('version' in value) || value.version !== 1 || !('userId' in value) || value.userId !== userId || !('orderId' in value) || value.orderId !== orderId || !('request' in value)) throw new Error('退款意图记录无效，请先联系支持核对，勿重复申请')
  const payload = value.request
  if (!payload || typeof payload !== 'object' || !('request_id' in payload) || typeof payload.request_id !== 'string' || !validId(payload.request_id) || !('reason' in payload) || typeof payload.reason !== 'string' || !payload.reason.trim() || payload.reason.length > 300) throw new Error('退款意图记录无效，请先联系支持核对，勿重复申请')
  return { version: 1, userId, orderId, request: { request_id: payload.request_id, reason: payload.reason } }
}
export function saveIntent(intent: RefundIntent) { Taro.setStorageSync(key(intent.userId, intent.orderId), intent) }
export function clearIntent(userId: string, orderId: string) { Taro.removeStorageSync(key(userId, orderId)) }
