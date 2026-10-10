import type { ResponseModelConsumerClosurePrecheckRead, ResponseModelConsumerLoginSessionsRead, ResponseModelConsumerSessionRevocationRead, ConsumerSessionTargets } from '@pinjie/api-client'
import { privateRequest } from '@/lib/session'
import type { RequestSignal } from '@/lib/cancellation'

export function readSessions(page: number, signal?: RequestSignal) {
  return privateRequest<ResponseModelConsumerLoginSessionsRead>(`/users/me/sessions?page=${page}&page_size=10`, { signal })
}
export function revokeSessions(target: ConsumerSessionTargets) {
  return privateRequest<ResponseModelConsumerSessionRevocationRead>('/users/me/sessions/revoke', { method: 'POST', data: target })
}
export function readRevocation(target: ConsumerSessionTargets) {
  return privateRequest<ResponseModelConsumerSessionRevocationRead>('/users/me/sessions/revocation-status', { method: 'POST', data: target })
}
export function readClosurePrecheck(signal?: RequestSignal) {
  return privateRequest<ResponseModelConsumerClosurePrecheckRead>('/users/me/closure-precheck', { signal })
}
