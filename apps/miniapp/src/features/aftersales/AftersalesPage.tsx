import { useState } from 'react'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { Text, Textarea, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { MiniappRefundRead, ResponseModelMiniappCheckoutIntentRead, ResponseModelMiniappRefundLookupRead, ResponseModelMiniappRefundRead, ResponseModelMiniappTradeOrderRead, ResponseModelPageResultMiniappRefundRead, ResponseModelRefundRequestRead } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateRequest, sessionScope, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'
import { clearIntent, loadIntent, saveIntent, validId } from './intent'
import type { RefundIntent } from './intent'

const reviewLabels: Record<string, string> = { requested: '待审核', approved: '审核通过', rejected: '审核拒绝', completed: '售后处理完成' }
const executionLabels: Record<MiniappRefundRead['execution_status'], string> = { not_started: '尚无资金执行记录', created: '已记录退款执行意图', processing: '渠道处理中', succeeded: '渠道已确认退款', abnormal: '渠道异常，请联系支持', unknown: '渠道结果未知，请继续查询', closed: '执行已关闭，请联系支持' }
function Progress({ refund }: { refund: MiniappRefundRead }) {
  return <><View className='trade-row spread'><Text className='section-title'>{reviewLabels[refund.status] ?? '未知审核状态'}</Text><Text className='price-small'>¥{refund.amount}</Text></View><View className='muted'>{refund.review_mode === 'automatic' ? '未接单自动审核' : '已接单人工审核'}</View><View>{executionLabels[refund.execution_status]}</View><View className='note'>{refund.funds_status === 'confirmed' ? '服务端已取得渠道退款确认事实' : refund.funds_status === 'no_funds' ? '零金额售后已完成，无资金退回' : '资金退回尚未确认，审核通过不代表到账'}</View>{refund.funds_confirmed_at && <View className='muted'>渠道确认时间：{new Date(refund.funds_confirmed_at).toLocaleString()}</View>}</>
}
function Apply() {
  const session = useSession()
  const orderId = useRouter().params.orderId
  const valid = validId(orderId)
  const [reason, setReason] = useState('')
  const [intent, setIntent] = useState<RefundIntent | null>(null)
  const [notice, setNotice] = useState('')
  const [acceptedId, setAcceptedId] = useState<string | null>(null)
  const stored = useQuery({ queryKey: ['private', 'refund-intent', session.epoch, orderId], enabled: valid, gcTime: 0, retry: false, queryFn: () => loadIntent(session.user!.id, orderId!) })
  const active = intent ?? stored.data ?? null
  const order = useQuery({ queryKey: ['private', 'order-detail', session.epoch, orderId], enabled: valid, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelMiniappTradeOrderRead>(`/trade-orders/${orderId}`, { signal }) })
  useDidShow(() => { if (valid) { void order.refetch(); void stored.refetch() } })
  const confirmed = async (id: string) => {
    if (session.epoch !== sessionScope()) return
    setAcceptedId(id)
    setNotice('服务端已确认受理，请在售后详情查询审核与资金事实。')
    clearIntent(session.user!.id, orderId!)
    setIntent(null)
    await queryClient.invalidateQueries({ queryKey: ['private', 'refund-intent'] })
    await queryClient.invalidateQueries({ queryKey: ['private', 'refunds'] })
    await queryClient.invalidateQueries({ queryKey: ['private', 'orders'] })
    await queryClient.invalidateQueries({ queryKey: ['private', 'order-detail'] })
    if (session.epoch !== sessionScope()) return
    await Taro.redirectTo({ url: `/subpackages/service/refund-detail/index?id=${id}` })
  }
  const lookup = useMutation({ mutationFn: async () => {
    if (!active) throw new Error('暂无待确认的退款意图')
    const result = await privateRequest<ResponseModelMiniappRefundLookupRead>(`/refunds/by-request/${active.request.request_id}`)
    if (result.state === 'found' && result.refund) await confirmed(result.refund.id)
    else setNotice('服务端暂未找到该请求。可以继续查询，或明确使用原请求号与原原因重试。')
  } })
  const submit = useMutation({ mutationFn: async () => {
    if (stored.isPending || stored.isError || !order.data) throw new Error('请先完成订单与本机意图读取')
    let current = active
    if (current) {
      const result = await privateRequest<ResponseModelMiniappRefundLookupRead>(`/refunds/by-request/${current.request.request_id}`)
      if (result.state === 'found' && result.refund) { await confirmed(result.refund.id); return }
    } else if (!order.data.can_refund || !reason.trim()) throw new Error('请检查退款资格并填写原因')
    const answer = await Taro.showModal({ title: current ? '使用原请求重试' : '整单退款', content: '覆盖全部商品和原运费。未接单自动审核，已接单人工审核。审核通过与资金退回分别确认。' })
    if (!answer.confirm || session.epoch !== sessionScope()) return
    if (!current) {
      const ticket = await privateRequest<ResponseModelMiniappCheckoutIntentRead>('/refunds/intent')
      current = { version: 1, userId: session.user!.id, orderId: orderId!, request: { request_id: ticket.request_id, reason: reason.trim() } }
      saveIntent(current)
      setIntent(current)
    }
    const result = await privateRequest<ResponseModelRefundRequestRead>(`/orders/${orderId}/refunds`, { method: 'POST', data: current.request })
    await confirmed(result.id)
  } })
  if (!valid) return <QueryState title='订单链接无效' />
  if (order.isPending || stored.isPending) return <QueryState title='正在读取退款资格与原请求' />
  if (order.isError || stored.isError) return <QueryState title='退款准备失败，勿重复申请' error={order.error ?? stored.error} retry={() => { void order.refetch(); void stored.refetch() }} />
  const busy = submit.isPending || lookup.isPending
  return <View className='page'><View className='title'>申请整单退款</View><View className='surface'><View className='section-title'>全量商品与原运费</View>{order.data.items.map((item) => <View className='order-line' key={item.id}><View>{item.product_name} × {item.quantity}</View><View className='muted'>¥{item.line_amount}</View></View>)}<View className='trade-row spread'><Text>商品金额</Text><Text>¥{order.data.items_amount}</Text></View><View className='trade-row spread'><Text>原运费</Text><Text>¥{order.data.freight_amount}</Text></View><View className='trade-row spread'><Text>整单金额</Text><Text className='price-small'>¥{order.data.total_amount}</Text></View><View className='note'>仅实物未发货或虚拟未交付可申请。最终资格与金额由服务端裁决。</View></View>
    {active ? <View className='surface'><View className='section-title'>原申请待确认</View><View className='wrap'>{active.request.reason}</View><View className='muted wrap'>请求号：{active.request.request_id}</View><View className='note'>原原因已锁定。先查询受理事实，保留原请求避免重复申请。</View></View> : <View className='surface'><View className='field-label'>退款原因</View><Textarea className='trade-textarea' maxlength={300} value={reason} disabled={busy} placeholder='请说明申请整单退款的原因' onInput={(event) => setReason(event.detail.value)} /><View className='muted'>{reason.length} / 300</View></View>}
    {(submit.error || lookup.error) && <QueryState title={acceptedId ? '申请已受理，本机记录处理或跳转未完成' : '申请结果未确认，请查询原请求'} error={submit.error ?? lookup.error} />}{notice && <View className='note'>{notice}</View>}
    {active && <Button block fill='outline' disabled={busy} loading={lookup.isPending} onClick={() => lookup.mutate()}>查询原申请结果</Button>}
    {acceptedId ? <Button block onClick={() => { void Taro.navigateTo({ url: `/subpackages/service/refund-detail/index?id=${acceptedId}` }) }}>查看已受理申请</Button> : <Button block disabled={busy || !active && (!order.data.can_refund || !reason.trim())} loading={submit.isPending} onClick={() => submit.mutate()}>{active ? '使用原请求号重试' : '提交整单退款申请'}</Button>}
    {!order.data.can_refund && !active && <View className='note'>当前订单不具备申请资格，已有申请请查看售后记录。</View>}
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: `/subpackages/service/refunds/index?orderId=${orderId}` }) }}>查看售后记录</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>获取帮助</Button>
  </View>
}
function List() {
  const session = useSession()
  const orderId = useRouter().params.orderId
  const valid = !orderId || validId(orderId)
  const [page, setPage] = useState(1)
  const query = useQuery({ queryKey: ['private', 'refunds', session.epoch, orderId, page], enabled: valid, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelPageResultMiniappRefundRead>(`/refunds?page=${page}&page_size=10${orderId ? `&order_id=${orderId}` : ''}`, { signal }) })
  useDidShow(() => { if (valid) void query.refetch() })
  if (!valid) return <QueryState title='订单链接无效' />
  return <View className='page'><View className='title'>售后记录</View>{query.isPending && <QueryState title='正在读取售后记录' />}{query.isError && <QueryState title='售后读取失败' error={query.error} retry={() => { void query.refetch() }} />}{query.data && !query.isError && <>{!query.data.items.length && <QueryState title='暂无售后记录' />}{query.data.items.map((refund) => <View className='surface' key={refund.id}><Progress refund={refund} /><View className='muted wrap'>{refund.reason}</View><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: `/subpackages/service/refund-detail/index?id=${refund.id}` }) }}>查看详情</Button></View>)}{query.data.total_pages > 1 && <View className='trade-row spread'><Button fill='outline' disabled={page === 1 || query.isFetching} onClick={() => setPage(page - 1)}>上一页</Button><Text>{page} / {query.data.total_pages}</Text><Button fill='outline' disabled={page >= query.data.total_pages || query.isFetching} onClick={() => setPage(page + 1)}>下一页</Button></View>}</>}<Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>获取帮助</Button></View>
}
function Detail() {
  const session = useSession()
  const id = useRouter().params.id
  const valid = validId(id)
  const query = useQuery({ queryKey: ['private', 'refund-detail', session.epoch, id], enabled: valid, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelMiniappRefundRead>(`/refunds/${id}`, { signal }) })
  const order = useQuery({ queryKey: ['private', 'order-detail', session.epoch, query.data?.order_id], enabled: !!query.data, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelMiniappTradeOrderRead>(`/trade-orders/${query.data?.order_id}`, { signal }) })
  useDidShow(() => { if (valid) void query.refetch() })
  if (!valid) return <QueryState title='售后链接无效' />
  if (query.isPending) return <QueryState title='正在读取售后详情' />
  if (query.isError) return <QueryState title='售后读取失败' error={query.error} retry={() => { void query.refetch() }} />
  const refund = query.data
  return <View className='page'><View className='title'>售后详情</View><View className='surface'><Progress refund={refund} /></View><View className='surface'><View className='section-title'>申请内容</View><View className='wrap'>{refund.reason}</View><View className='muted wrap'>申请号：{refund.id}</View><View className='muted'>申请时间：{new Date(refund.created_at).toLocaleString()}</View><View className='field-label'>审核意见</View><View className='wrap'>{refund.review_note ?? '尚无审核意见'}</View>{refund.reviewed_at && <View className='muted'>审核时间：{new Date(refund.reviewed_at).toLocaleString()}</View>}{refund.completed_at && <View className='muted'>处理完成：{new Date(refund.completed_at).toLocaleString()}</View>}</View><View className='surface'><View className='section-title'>整单范围</View>{order.isPending && <QueryState title='正在读取订单明细' />}{order.isError && <QueryState title='订单明细读取失败' error={order.error} retry={() => { void order.refetch() }} />}{order.data && !order.isError && order.data.items.map((item) => <View className='order-line' key={item.id}>{item.product_name} × {item.quantity}<View className='muted'>¥{item.line_amount}</View></View>)}<View>商品：¥{refund.items_amount}</View><View>原运费：¥{refund.freight_amount}</View></View><Button block fill='outline' onClick={() => { void query.refetch(); void order.refetch() }}>刷新审核与资金事实</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: `/subpackages/trade/order-detail/index?id=${refund.order_id}` }) }}>查看原订单</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>联系支持</Button></View>
}
export function RefundApplyPage() { const session = useSession(); return <AuthGate><Apply key={session.epoch} /></AuthGate> }
export function RefundsPage() { const session = useSession(); return <AuthGate><List key={session.epoch} /></AuthGate> }
export function RefundDetailPage() { const session = useSession(); return <AuthGate><Detail key={session.epoch} /></AuthGate> }
