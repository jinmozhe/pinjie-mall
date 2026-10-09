import { useState } from 'react'
import Taro, { useDidShow, usePullDownRefresh, useRouter } from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { OrderRead, ResponseModelOrderRead, ResponseModelPageResultOrderRead } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateRequest, sessionScope, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'

const statusLabel: Record<string, string> = { pending_payment: '待付款', paid: '已付款', cancelled: '已取消' }
const filters = [{ value: '', label: '全部' }, { value: 'pending_payment', label: '待付款' }, { value: 'paid', label: '已付款' }, { value: 'cancelled', label: '已取消' }]
function Summary({ order }: { order: OrderRead }) {
  return <><View className='trade-row spread'><Text className='label'>{statusLabel[order.status] ?? order.status}</Text><Text className='muted'>{order.created_at.slice(0, 10)}</Text></View>{order.items.map((item) => <View className='order-line' key={item.id}><View>{item.product_name}</View><View className='muted'>{Object.values(item.specifications).join(' / ') || '默认规格'} · {item.quantity} 件</View><View>¥{item.unit_price} / 件</View></View>)}<View className='trade-row spread'><Text>订单金额</Text><Text className='price-small'>¥{order.total_amount}</Text></View></>
}
function List() {
  const session = useSession()
  const route = useRouter()
  const [status, setStatus] = useState(filters.some((filter) => filter.value === route.params.status) ? route.params.status ?? '' : '')
  const [page, setPage] = useState(1)
  const query = useQuery({ queryKey: ['private', 'orders', session.epoch, status, page], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelPageResultOrderRead>(`/orders?page=${page}&page_size=10${status ? `&status=${status}` : ''}`, { signal }) })
  useDidShow(() => { void query.refetch() })
  usePullDownRefresh(() => { void query.refetch().finally(() => Taro.stopPullDownRefresh()) })
  return <View className='page'><View className='title'>我的订单</View><View className='category-strip'>{filters.map((filter) => <Button key={filter.value} type={filter.value === status ? 'primary' : 'default'} fill='outline' onClick={() => { setStatus(filter.value); setPage(1) }}>{filter.label}</Button>)}</View>
    {query.isPending && <QueryState title='正在读取订单' />}{query.isError && <QueryState title='订单读取失败' error={query.error} retry={() => { void query.refetch() }} />}
    {query.data && !query.isError && <>{!query.data.items.length && <QueryState title='暂无相关订单' />}{query.data.items.map((order) => <View className='surface' key={order.id}><Summary order={order} /><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: `/subpackages/trade/order-detail/index?id=${order.id}` }) }}>查看详情</Button></View>)}{query.data.total_pages > 1 && <View className='trade-row spread'><Button fill='outline' disabled={page === 1 || query.isFetching} onClick={() => setPage(page - 1)}>上一页</Button><Text>{page} / {query.data.total_pages}</Text><Button fill='outline' disabled={page >= query.data.total_pages || query.isFetching} onClick={() => setPage(page + 1)}>下一页</Button></View>}</>}
  </View>
}
function Detail() {
  const session = useSession()
  const id = useRouter().params.id
  const valid = !!id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
  const query = useQuery({ queryKey: ['private', 'order-detail', session.epoch, id], enabled: valid, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelOrderRead>(`/orders/${id}`, { signal }) })
  useDidShow(() => { if (valid) void query.refetch() })
  const cancel = useMutation({ mutationFn: async () => {
    const answer = await Taro.showModal({ title: '取消订单', content: '确认取消这笔待付款订单并释放占用库存？' })
    if (!answer.confirm || session.epoch !== sessionScope()) return
    await privateRequest<ResponseModelOrderRead>(`/orders/${id}/cancel`, { method: 'POST' })
  }, onSettled: async () => { await queryClient.invalidateQueries({ queryKey: ['private', 'orders'] }); await query.refetch() } })
  if (!valid) return <QueryState title='订单链接无效' />
  if (query.isPending) return <QueryState title='正在读取订单' />
  if (query.isError) return <QueryState title='订单读取失败' error={query.error} retry={() => { void query.refetch() }} />
  const order = query.data
  const address = order.address_snapshot
  const addressText = (name: string) => typeof address?.[name] === 'string' ? address[name] : ''
  return <View className='page'><View className='title'>订单详情</View>{cancel.error && <QueryState title='取消结果未确认，请读取最新状态' error={cancel.error} />}
    <View className='surface'><Summary order={order} /></View>
    {address && <View className='surface'><View className='section-title'>收货信息</View><View>{addressText('receiver_name')} · {addressText('mobile')}</View><View className='muted'>{addressText('province')}{addressText('city')}{addressText('district')}{addressText('street_address')}</View></View>}
    <View className='surface'><View className='trade-row spread'><Text>商品金额</Text><Text>¥{order.items_amount}</Text></View><View className='trade-row spread'><Text>运费</Text><Text>¥{order.freight_amount}</Text></View><View className='field-label'>订单号</View><View className='muted wrap'>{order.id}</View><View className='muted'>创建时间 {new Date(order.created_at).toLocaleString()}</View>{order.status === 'pending_payment' && <View className='muted'>付款截止 {new Date(order.expires_at).toLocaleString()}</View>}{order.settlement_kind === 'zero_amount' && <View className='note'>零金额订单由服务端确认成交</View>}</View>
    {order.status === 'pending_payment' && <><View className='note'>微信支付尚未开放。到期状态以服务端为准，请刷新确认。</View><Button block fill='outline' disabled={cancel.isPending} loading={cancel.isPending} onClick={() => cancel.mutate()}>取消订单</Button></>}
    <Button block fill='outline' onClick={() => { void query.refetch() }}>刷新订单状态</Button>
  </View>
}
export function OrdersPage() { const session = useSession(); return <AuthGate><List key={session.epoch} /></AuthGate> }
export function OrderDetailPage() { const session = useSession(); return <AuthGate><Detail key={session.epoch} /></AuthGate> }
