import Taro from '@tarojs/taro'
import { invitationCode, parseReferralIntent } from './domain'

const key = (userId: string) => `pinjie.referral.${userId}`
export function loadIntent(userId: string) { return parseReferralIntent(Taro.getStorageSync(key(userId)), userId) }
export function saveIntent(userId: string, code: string) {
  if (invitationCode(code) !== code) throw new Error('推荐码格式无效')
  Taro.setStorageSync(key(userId), { version: 1, userId, code })
}
export function clearIntent(userId: string) { Taro.removeStorageSync(key(userId)) }
