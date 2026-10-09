import type { MiniappSessionRevocationRead, MiniappSessionTargets } from '@pinjie/api-client'

export function validSessionIds(value: unknown): value is string[] {
  return Array.isArray(value) && value.length >= 1 && value.length <= 100 && new Set(value).size === value.length && value.every((id) => typeof id === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id))
}

export function revocationConfirmed(target: MiniappSessionTargets, result: MiniappSessionRevocationRead): boolean {
  if (result.sessions.length !== target.session_ids.length || new Set(result.sessions.map((item) => item.id)).size !== target.session_ids.length || result.sessions.some((item) => !target.session_ids.includes(item.id))) throw new Error('返回的会话目标不匹配，请联系支持核对')
  return result.sessions.every((item) => item.state === 'revoked' || item.state === 'expired')
}
