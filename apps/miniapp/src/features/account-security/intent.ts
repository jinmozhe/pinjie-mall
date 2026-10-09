import Taro from '@tarojs/taro'
import type { MiniappSessionTargets } from '@pinjie/api-client'
import { validSessionIds } from './domain'

export type RevocationIntent = { version: 1; userId: string; target: MiniappSessionTargets }
const key = (userId: string) => `pinjie.session-revocation.${userId}`

export function loadRevocation(userId: string): RevocationIntent | null {
  const value: unknown = Taro.getStorageSync(key(userId))
  if (value === '' || value === undefined || value === null) return null
  if (typeof value !== 'object' || !('version' in value) || value.version !== 1 || !('userId' in value) || value.userId !== userId || !('target' in value) || !value.target || typeof value.target !== 'object' || !('session_ids' in value.target) || !validSessionIds(value.target.session_ids)) throw new Error('原会话撤销记录无效，请联系支持核对，勿提交新目标')
  return { version: 1, userId, target: { session_ids: [...value.target.session_ids] } }
}
export function saveRevocation(intent: RevocationIntent) { Taro.setStorageSync(key(intent.userId), intent) }
export function clearRevocation(userId: string) { Taro.removeStorageSync(key(userId)) }
