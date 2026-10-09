import { describe, expect, it } from 'vitest'
import { revocationConfirmed, validSessionIds } from './domain'

const first = '01990000-0000-7000-8000-000000000001'
const second = '01990000-0000-7000-8000-000000000002'
describe('fixed session revocation targets', () => {
  it('rejects malformed, duplicate and unbounded target collections', () => {
    expect(validSessionIds([first])).toBe(true)
    for (const ids of [[], [first, first], ['invalid'], Array(101).fill(first), null]) expect(validSessionIds(ids)).toBe(false)
  })
  it('requires exactly the original targets and terminal facts', () => {
    const target = { session_ids: [first, second] }
    expect(revocationConfirmed(target, { sessions: [{ id: second, state: 'expired' }, { id: first, state: 'revoked' }] })).toBe(true)
    expect(revocationConfirmed(target, { sessions: [{ id: first, state: 'revoked' }, { id: second, state: 'active' }] })).toBe(false)
    expect(revocationConfirmed(target, { sessions: [{ id: first, state: 'revoked' }, { id: second, state: 'not_found' }] })).toBe(false)
    expect(() => revocationConfirmed(target, { sessions: [{ id: first, state: 'revoked' }] })).toThrow('不匹配')
    expect(() => revocationConfirmed(target, { sessions: [{ id: first, state: 'revoked' }, { id: first, state: 'revoked' }] })).toThrow('不匹配')
  })
})
