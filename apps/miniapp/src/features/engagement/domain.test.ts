import { describe, expect, it } from 'vitest'
import { invitationCode, parseReferralIntent, referralPath } from './domain'

describe('referral intent boundary', () => {
  it('normalizes a code and rejects URLs, encoding, duplicates and oversized inputs', () => {
    expect(invitationCode(' abc12345 ')).toBe('ABC12345')
    for (const value of [null, 12, ['ABC12345', 'DEF12345'], '', 'short', 'A'.repeat(17), 'A'.repeat(1000), 'ABC%31345', 'ABC12345&invite=DEF12345', 'https://example.test/?invite=ABC12345', '测试邀请码测试邀请码']) expect(invitationCode(value)).toBeNull()
    expect(referralPath('abc12345')).toBe('/subpackages/finance/referral/index?invite=ABC12345')
    expect(() => referralPath('../unsafe')).toThrow()
  })
  it('isolates pending writes by user and fails closed on corrupt recovery records', () => {
    expect(parseReferralIntent('', 'owner')).toBeNull()
    expect(parseReferralIntent({ version: 1, userId: 'owner', code: 'ABC12345' }, 'owner')).toBe('ABC12345')
    for (const value of [{ version: 1, userId: 'other', code: 'ABC12345' }, { version: 2, userId: 'owner', code: 'ABC12345' }, { version: 1, userId: 'owner', code: 'abc12345' }, { version: 1, userId: 'owner', code: 'broken' }, false]) expect(() => parseReferralIntent(value, 'owner')).toThrow()
  })
})
