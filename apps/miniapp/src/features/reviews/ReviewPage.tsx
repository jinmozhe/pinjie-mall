import { useState } from 'react'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { Textarea, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { ResponseModelConsumerTradeOrderRead, ResponseModelProductReviewRead } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateRequest, sessionScope, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'

const validId = (id: string | undefined) => !!id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
function Content() {
  const session = useSession()
  const { orderId, itemId } = useRouter().params
  const valid = validId(orderId) && validId(itemId)
  const [rating, setRating] = useState(5)
  const [content, setContent] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const query = useQuery({ queryKey: ['private', 'order-detail', session.epoch, orderId], enabled: valid, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerTradeOrderRead>(`/orders/${orderId}`, { signal }) })
  useDidShow(() => { if (valid) void query.refetch() })
  const item = query.data?.item_reviews.find((row) => row.order_item_id === itemId)
  const submit = useMutation({ mutationFn: async () => {
    if (!item?.can_review || submitted) throw new Error('请先确认评价资格和已提交结果')
    const answer = await Taro.showModal({ title: '提交评价', content: '评价会公开展示，每条已交付明细只能评价一次，请勿填写手机号、地址等个人信息。' })
    if (!answer.confirm || session.epoch !== sessionScope()) return
    setSubmitted(true)
    await privateRequest<ResponseModelProductReviewRead>(`/order-items/${itemId}/review`, { method: 'POST', data: { rating, content } })
    setAccepted(true)
    await queryClient.invalidateQueries({ queryKey: ['catalog-detail'] })
  }, onSettled: async () => { await query.refetch() } })
  if (!valid) return <QueryState title='评价链接无效' />
  if (query.isPending) return <QueryState title='正在读取本人评价资格' />
  if (query.isError) return <QueryState title={accepted ? '评价已提交，最新事实读取失败' : '评价资格读取失败'} error={query.error} retry={() => { void query.refetch() }} />
  if (!item) return <QueryState title='当前订单没有此商品明细' />
  const name = query.data.items.find((line) => line.id === itemId)?.product_name
  return <View className='page'><View className='title'>{item.review ? '我的评价' : '评价商品'}</View><View className='surface'><View className='section-title'>{name}</View>{item.review ? <><View>{item.review.rating} / 5 星</View><View className='wrap'>{item.review.content || '未填写文字评价'}</View><View className='muted'>评价时间：{new Date(item.review.published_at).toLocaleString()}</View></> : <><View className='field-label'>评分</View><View className='category-strip'>{[1, 2, 3, 4, 5].map((star) => <Button key={star} fill='outline' type={rating === star ? 'primary' : 'default'} disabled={submitted || submit.isPending || !item.can_review} onClick={() => setRating(star)}>{star} 星</Button>)}</View><View className='field-label'>评价内容</View><Textarea className='trade-textarea' maxlength={1000} value={content} disabled={submitted || submit.isPending || !item.can_review} placeholder='分享商品与服务体验，请勿填写个人信息' onInput={(event) => setContent(event.detail.value)} /><View className='muted'>{content.length} / 1000</View></>}</View>
    {!item.review && !item.can_review && <View className='note'>仅本人已交付商品可评价一次。</View>}
    {!item.review && submitted && <View className='note'>{accepted ? '服务端已确认评价提交，请读取最新评价事实。' : '评价提交结果尚未确认。请查询本人已评价事实或联系支持，勿重复提交。'}</View>}
    {!item.review && submit.error && <QueryState title='评价提交未确认' error={submit.error} />}
    {!item.review && <Button block loading={submit.isPending} disabled={!item.can_review || submitted || submit.isPending} onClick={() => submit.mutate()}>提交评价</Button>}
    <Button block fill='outline' disabled={submit.isPending} onClick={() => { void query.refetch() }}>查询最新评价事实</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>获取帮助</Button>
  </View>
}
export function ReviewPage() { const session = useSession(); return <AuthGate><Content key={session.epoch} /></AuthGate> }
