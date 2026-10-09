import { describe, expect, it } from 'vitest'
import type { PublicSkuRead } from '@pinjie/api-client'
import { canSelect, matchingSkus, resolvedSku, specGroups } from './sku'

function variant(id: string, specifications: Record<string, string>, active = true): PublicSkuRead {
  return { id, code: id, sku_no: 1, specifications, price: '10.00', market_price: null, wholesale_prices: [], weight_grams: null, is_active: active }
}

describe('商品规格选择', () => {
  const skus = [variant('red-small', { 颜色: '红', 尺码: '小' }), variant('blue-large', { 颜色: '蓝', 尺码: '大' }), variant('disabled', { 颜色: '绿', 尺码: '小' }, false)]
  it('不把停用规格加入可选值，也不让部分选择成为完整 SKU', () => {
    expect(specGroups(skus)).toEqual([{ name: '颜色', values: ['红', '蓝'] }, { name: '尺码', values: ['小', '大'] }])
    expect(resolvedSku(skus, { 颜色: '红' })).toBeUndefined()
    expect(resolvedSku(skus, { 颜色: '红', 尺码: '小' })?.id).toBe('red-small')
  })
  it('拒绝不存在的组合，取消另一组选值后允许切换', () => {
    expect(canSelect(skus, { 颜色: '红', 尺码: '小' }, '颜色', '蓝')).toBe(false)
    expect(canSelect(skus, { 颜色: '红' }, '颜色', '蓝')).toBe(true)
    expect(matchingSkus(skus, { 颜色: '绿' })).toEqual([])
  })
  it('无规格商品解析默认 SKU；空列表与停用 SKU 保持不可售', () => {
    expect(resolvedSku([variant('default', {})], {})?.id).toBe('default')
    expect(resolvedSku([], {})).toBeUndefined()
    expect(resolvedSku([variant('default', {}, false)], {})).toBeUndefined()
  })
})
