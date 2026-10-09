import type { CartItemInput, ResponseModelCartItemRead } from '@pinjie/api-client'
import { privateRequest } from '@/lib/session'
import { queryClient } from '@/lib/query'

export async function addToCart(data: CartItemInput) {
  const result = await privateRequest<ResponseModelCartItemRead>('/cart-items', { method: 'POST', data })
  await queryClient.invalidateQueries({ queryKey: ['private', 'cart'] })
  return result
}
