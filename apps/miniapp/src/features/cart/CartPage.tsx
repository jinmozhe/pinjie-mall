import { useEffect } from 'react'
import Taro, { useDidShow, usePullDownRefresh } from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { ConsumerCartItemRead, CartItemUpdate, ResponseModelListConsumerCartItemRead, ResponseModelCartItemRead, ResponseModelNoneType } from '@pinjie/api-client'
import { Button } from '@/components/Button'
import { AuthGate } from '@/components/AuthGate'
import { ProductImage } from '@/components/ProductImage'
import { QueryState } from '@/components/QueryState'
import { queryClient } from '@/lib/query'
import { privateRequest, useSession } from '@/lib/session'
import { startCheckout } from '@/features/checkout'

function useCart() {
  const session = useSession()
  return useQuery({ queryKey: ['private', 'cart', session.epoch], enabled: !!session.user, gcTime: 0,
    queryFn: ({ signal }) => privateRequest<ResponseModelListConsumerCartItemRead>('/cart-items', { signal }) })
}
export function CartBadge() {
  const session = useSession()
  const query = useCart()
  useEffect(() => {
    const quantity = query.data?.reduce((total, item) => total + item.quantity, 0) ?? 0
    const operation = session.user && !query.isError && quantity > 0 ? Taro.setTabBarBadge({ index: 2, text: quantity > 99 ? '99+' : String(quantity) }) : Taro.removeTabBarBadge({ index: 2 })
    void operation.catch(() => { /* App startup can precede the native tab bar. */ })
  }, [query.data, query.isError, session.user])
  useDidShow(() => { if (session.user) void query.refetch() })
  return null
}
function Content() {
  const query = useCart()
  const mutation = useMutation({
    mutationFn: async (action: { item: ConsumerCartItemRead; patch?: CartItemUpdate }) => {
      if (action.patch) return privateRequest<ResponseModelCartItemRead>(`/cart-items/${action.item.id}`, { method: 'PATCH', data: action.patch })
      await privateRequest<ResponseModelNoneType>(`/cart-items/${action.item.id}`, { method: 'DELETE' })
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['private', 'cart'] }),
  })
  const checkout = useMutation({ mutationFn: () => {
    const items = (query.data ?? []).filter((item) => item.selected && !item.invalid_reason)
    const type = items[0]?.product_type
    if (!type || items.some((item) => item.product_type !== type)) throw new Error('实物与虚拟商品请分开结算')
    return startCheckout(items.map((item) => ({ sku_id: item.sku_id, quantity: item.quantity })), type)
  } })
  useDidShow(() => { void query.refetch() })
  usePullDownRefresh(() => { void query.refetch().finally(() => Taro.stopPullDownRefresh()) })
  if (query.isPending) return <QueryState title='正在读取购物车' />
  if (query.isError) return <QueryState title='购物车读取失败' error={query.error} retry={() => { void query.refetch() }} />
  const selected = query.data.filter((item) => item.selected && !item.invalid_reason)
  return <View className='page trade-page'>
    <View className='title'>购物车</View><View className='muted'>共 {query.data.length} 种商品 · 成交金额以结算报价为准</View>
    {(mutation.error || checkout.error) && <QueryState title='操作未完成，请重新读取后确认' error={mutation.error ?? checkout.error} />}
    {!query.data.length && <QueryState title='购物车空空的' detail='去挑选喜欢的商品吧' />}
    {query.data.map((item) => <View className='surface' key={item.id}>
      <View className='trade-row'><Button fill='outline' disabled={mutation.isPending || !!item.invalid_reason && !item.selected} onClick={() => mutation.mutate({ item, patch: { revision: item.revision, selected: !item.selected } })}>{item.selected ? '已选' : '选择'}</Button>
        <View className='trade-thumb' onClick={() => { if (item.product_id) void Taro.navigateTo({ url: `/subpackages/catalog/detail/index?id=${item.product_id}` }) }}><ProductImage url={item.image_url ?? undefined} /></View>
        <View className='trade-info'><View>{item.product_name}</View><View className='muted'>{Object.values(item.specifications).join(' / ') || '默认规格'}</View><View className='price-small'>{item.unit_price == null ? '当前不可售' : `¥${item.unit_price}`}</View></View>
      </View>
      {item.invalid_reason && <View className='note'>{item.invalid_reason}</View>}
      <View className='trade-row spread'><View className='trade-row'><Button fill='outline' disabled={mutation.isPending || item.quantity <= 1 || item.available_quantity < 1} onClick={() => mutation.mutate({ item, patch: { revision: item.revision, quantity: item.quantity - 1 } })}>−</Button><Text>{item.quantity}</Text><Button fill='outline' disabled={mutation.isPending || !!item.invalid_reason || item.quantity >= Math.min(999, item.available_quantity)} onClick={() => mutation.mutate({ item, patch: { revision: item.revision, quantity: item.quantity + 1 } })}>＋</Button></View>
        <Button fill='outline' disabled={mutation.isPending} onClick={() => { void Taro.showModal({ title: '移除商品', content: `确认从购物车移除 ${item.product_name}？` }).then((result) => { if (result.confirm) mutation.mutate({ item }) }) }}>移除</Button></View>
    </View>)}
    <View className='trade-footer'><View className='muted'>已选 {selected.reduce((total, item) => total + item.quantity, 0)} 件可售商品</View><Button type='primary' block disabled={!selected.length || selected.length > 50 || mutation.isPending || checkout.isPending} loading={checkout.isPending} onClick={() => checkout.mutate()}>去结算</Button>{selected.length > 50 && <Text className='muted'>单次最多结算 50 种商品</Text>}</View>
  </View>
}
export function CartPage() { return <AuthGate><Content /></AuthGate> }
