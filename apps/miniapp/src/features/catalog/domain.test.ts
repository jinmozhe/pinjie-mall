import { describe, expect, it } from 'vitest'
import type { CategoryRead, PageResultPublicProductRead, PublicProductRead, PublicSkuRead } from '@pinjie/api-client'
import { categoryPath, nextProductPage, productPrice, uniqueProducts } from './domain'

const sku = (price: string, market: string | null = null): PublicSkuRead => ({
  id: price, code: price, sku_no: 1, specifications: {}, price, market_price: market,
  wholesale_prices: [], weight_grams: null, is_active: true,
})
const product = (id: string, skus: PublicSkuRead[] = []): PublicProductRead => ({
  id, name: id, description: '', description_format: 'legacy', product_type: 'physical',
  category_id: 'leaf', brand_id: null, images: [], skus, attributes: [],
})
const page = (number: number, ids: string[], total: number): PageResultPublicProductRead => ({
  page: number, page_size: 20, total, total_pages: Math.ceil(total / 20), items: ids.map((id) => product(id)),
})

describe('分类范围与公开商品展示', () => {
  it('从叶级分类恢复一级高亮及完整搜索范围，不依赖接口的树形排序', () => {
    const categories: CategoryRead[] = [
      { id: 'leaf', name: '大米', parent_id: 'middle', revision: 1 },
      { id: 'other', name: '日化', revision: 1 },
      { id: 'root', name: '生鲜粮油', revision: 1 },
      { id: 'middle', name: '粮油', parent_id: 'root', revision: 1 },
    ]
    expect(categoryPath(categories, 'leaf').map((item) => item.name)).toEqual(['生鲜粮油', '粮油', '大米'])
    expect(categoryPath(categories, 'removed')).toEqual([])
    expect(categoryPath(categories)).toEqual([])
  })

  it('末页和空页停止继续翻页，跨页重复商品只展示一次', () => {
    expect(nextProductPage(page(1, ['a'], 21))).toBe(2)
    expect(nextProductPage(page(2, ['b'], 21))).toBeUndefined()
    expect(nextProductPage(page(2, [], 100))).toBeUndefined()
    expect(uniqueProducts([page(1, ['a', 'b'], 3), page(2, ['b', 'c'], 3)]).map((item) => item.id)).toEqual(['a', 'b', 'c'])
  })

  it('不混用不同 SKU 的参考价，金额按十进制比较且不伪造零价', () => {
    expect(productPrice(product('one', [sku('9.90', '19.90')]))).toEqual({ label: '¥9.90', market: '19.90', multiple: false })
    expect(productPrice(product('multi', [sku('99.00', '199.00'), sku('9.90', '19.90')]))).toEqual({ label: '¥9.90 起', market: undefined, multiple: true })
    expect(productPrice(product('invalid-market', [sku('9.90', '9.9')])).market).toBeUndefined()
    expect(productPrice(product('huge', [sku('999999999999999999.99', '1000000000000000000.00')])).market).toBe('1000000000000000000.00')
    expect(productPrice(product('none', [{ ...sku('10'), is_active: false }])).label).toBe('暂无可售规格')
  })
})
