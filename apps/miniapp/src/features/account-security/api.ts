import type { ResponseModelMiniappClosurePrecheckRead, ResponseModelMiniappLoginSessionsRead, ResponseModelMiniappSessionRevocationRead, MiniappSessionTargets } from '@pinjie/api-client'
import { privateRequest } from '@/lib/session'
import type { RequestSignal } from '@/lib/cancellation'

export function readSessions(page: number, signal?: RequestSignal) {
  return privateRequest<ResponseModelMiniappLoginSessionsRead>(`/sessions?page=${page}&page_size=10`, { signal })
}
export function revokeSessions(target: MiniappSessionTargets) {
  return privateRequest<ResponseModelMiniappSessionRevocationRead>('/sessions/revoke', { method: 'POST', data: target })
}
export function readRevocation(target: MiniappSessionTargets) {
  return privateRequest<ResponseModelMiniappSessionRevocationRead>('/sessions/revocation-status', { method: 'POST', data: target })
}
export function readClosurePrecheck(signal?: RequestSignal) {
  return privateRequest<ResponseModelMiniappClosurePrecheckRead>('/account/closure-precheck', { signal })
}
