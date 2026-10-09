import { describe, expect, it } from 'vitest'
import { compareMoney, priceLabel } from './money'

describe('公开价格展示', () => {
  it('按十进制值比较，不按文本排序或使用浮点数', () => {
    expect(priceLabel(['100.00', '9.99', '10.00'])).toBe('¥9.99 起')
    expect(compareMoney('999999999999999999.99', '1000000000000000000.00')).toBeLessThan(0)
    expect(compareMoney('0.10', '0.1')).toBe(0)
  })
  it('保留服务端金额文本；无可售 SKU 不伪造零元商品', () => {
    expect(priceLabel(['0.00'])).toBe('¥0.00')
    expect(priceLabel(['9.90', '9.90'])).toBe('¥9.90')
    expect(priceLabel([])).toBe('暂无可售规格')
  })
})
