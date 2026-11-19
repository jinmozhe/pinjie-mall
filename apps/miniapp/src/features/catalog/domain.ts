import type { CategoryRead, PageResultPublicProductRead, PublicProductRead } from '@pinjie/api-client'
import { compareMoney, priceLabel } from '../../lib/money'

export const CATEGORY_PAGE_SIZE = 20
export const CATEGORY_MAX_PAGES = 5

export function categoryPath(categories: CategoryRead[], id?: string): CategoryRead[] {
  const byId = new Map(categories.map((category) => [category.id, category]))
  const path: CategoryRead[] = []
  const seen = new Set<string>()
  let current = id ? byId.get(id) : undefined
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    path.unshift(current)
    current = current.parent_id ? byId.get(current.parent_id) : undefined
  }
  return path
}

export function nextProductPage(page: PageResultPublicProductRead) {
  return page.items.length && page.page * page.page_size < page.total ? page.page + 1 : undefined
}

export function uniqueProducts(pages: PageResultPublicProductRead[]) {
  const seen = new Set<string>()
  return pages.flatMap((page) => page.items).filter((product) => {
    if (seen.has(product.id)) return false
    seen.add(product.id)
    return true
  })
}

export function productPrice(product: PublicProductRead) {
  const skus = product.skus.filter((sku) => sku.is_active)
  const single = skus.length === 1 ? skus[0] : undefined
  return {
    label: priceLabel(skus.map((sku) => sku.price)),
    multiple: skus.length > 1,
    market: single?.market_price && compareMoney(single.market_price, single.price) > 0 ? single.market_price : undefined,
  }
}
