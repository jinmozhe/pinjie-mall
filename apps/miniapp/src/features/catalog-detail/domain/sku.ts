import type { PublicSkuRead } from '@pinjie/api-client'

export type Selection = Record<string, string>

export function specGroups(skus: PublicSkuRead[]): { name: string; values: string[] }[] {
  const groups = new Map<string, Set<string>>()
  for (const sku of skus.filter((item) => item.is_active)) {
    for (const [name, value] of Object.entries(sku.specifications)) {
      if (!groups.has(name)) groups.set(name, new Set())
      groups.get(name)?.add(value)
    }
  }
  return [...groups].map(([name, values]) => ({ name, values: [...values] }))
}

export function matchingSkus(skus: PublicSkuRead[], selected: Selection): PublicSkuRead[] {
  return skus.filter((sku) => sku.is_active && Object.entries(selected).every(([name, value]) => sku.specifications[name] === value))
}

export function resolvedSku(skus: PublicSkuRead[], selected: Selection): PublicSkuRead | undefined {
  const matches = matchingSkus(skus, selected)
  return matches.length === 1 && Object.keys(matches[0].specifications).every((name) => selected[name] !== undefined) ? matches[0] : undefined
}

export function canSelect(skus: PublicSkuRead[], selected: Selection, name: string, value: string): boolean {
  return matchingSkus(skus, { ...selected, [name]: value }).length > 0
}
