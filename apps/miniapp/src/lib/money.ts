export function compareMoney(left: string, right: string): number {
  const [aWhole, aFraction = ''] = left.split('.')
  const [bWhole, bFraction = ''] = right.split('.')
  const a = aWhole.replace(/^0+(?=\d)/, '')
  const b = bWhole.replace(/^0+(?=\d)/, '')
  if (a.length !== b.length) return a.length - b.length
  if (a !== b) return a < b ? -1 : 1
  const width = Math.max(aFraction.length, bFraction.length)
  return aFraction.padEnd(width, '0') < bFraction.padEnd(width, '0') ? -1 : aFraction.padEnd(width, '0') > bFraction.padEnd(width, '0') ? 1 : 0
}

export function priceLabel(prices: string[]): string {
  if (!prices.length) return '暂无可售规格'
  const ordered = [...prices].sort(compareMoney)
  return `¥${ordered[0]}${compareMoney(ordered[0], ordered[ordered.length - 1]) !== 0 ? ' 起' : ''}`
}
