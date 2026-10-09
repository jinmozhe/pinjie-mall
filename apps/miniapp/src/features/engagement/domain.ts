// Router parameters are untrusted intents. Never decode repeatedly or follow a supplied URL.
export function invitationCode(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 32) return null
  const code = value.trim().toUpperCase()
  return /^[A-Z0-9]{8,16}$/.test(code) ? code : null
}
export function referralPath(code: unknown): string {
  const valid = invitationCode(code)
  if (!valid) throw new Error('本人邀请码无效，请刷新档案')
  return `/subpackages/finance/referral/index?invite=${encodeURIComponent(valid)}`
}
export function parseReferralIntent(value: unknown, userId: string): string | null {
  if (value === '' || value === null || value === undefined) return null
  if (typeof value !== 'object' || !('version' in value) || value.version !== 1 || !('userId' in value) || value.userId !== userId || !('code' in value)) throw new Error('推荐绑定恢复记录无效，请联系支持核对，勿重复绑定')
  const code = invitationCode(value.code)
  if (!code || code !== value.code) throw new Error('推荐绑定恢复记录无效，请联系支持核对，勿重复绑定')
  return code
}
