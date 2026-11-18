import { useEffect, useRef, useState } from 'react'
import Taro, { useDidHide, useDidShow } from '@tarojs/taro'
import { View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { PaymentAttemptRead, ResponseModelOperationIntentRead, ResponseModelPaymentAttemptRead, ResponseModelPaymentStatusRead } from '@pinjie/api-client'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateRequest, sessionScope, useSession } from '@/lib/session'
import { canInvokePayment, isPaymentRequestId, shouldPollPayment } from './payment-domain'

const labels: Record<string, string> = {
  created: '支付准备中，请查询结果', pending: '待付款，结果以服务端为准',
  unknown: '支付结果确认中，请勿重复付款', succeeded: '渠道已确认付款，订单正在更新',
  unavailable: '微信支付尚未开放', closed: '本次支付已关闭',
}

export function PaymentPanel({ orderId, refreshOrder }: { orderId: string; refreshOrder: () => Promise<unknown> }) {
  const session = useSession()
  const userId = session.user?.id
  const storageKey = `pinjie.payment.${userId}.${orderId}`
  const [visible, setVisible] = useState(true)
  const [pollUntil, setPollUntil] = useState(() => Date.now() + 60000)
  const [notice, setNotice] = useState('')
  const lock = useRef(false)
  const mounted = useRef(true)
  const foreground = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; foreground.current = false }
  }, [])
  const query = useQuery({
    queryKey: ['private', 'payment', session.epoch, orderId], gcTime: 0,
    queryFn: ({ signal }) => privateRequest<ResponseModelPaymentStatusRead>(`/orders/${orderId}/payment-status`, { signal }),
    refetchInterval: (state) => shouldPollPayment(state.state.data?.attempt?.status, visible, pollUntil, Date.now()) ? 3000 : false,
  })
  useDidShow(() => { foreground.current = true; setVisible(true); setPollUntil(Date.now() + 60000); void query.refetch(); void refreshOrder() })
  useDidHide(() => { foreground.current = false; setVisible(false) })
  useEffect(() => {
    if (visible && query.data?.attempt?.status === 'succeeded') void refreshOrder()
  }, [visible, query.dataUpdatedAt, query.data?.attempt?.status, refreshOrder])
  const refresh = useMutation({ mutationFn: async () => {
    setPollUntil(Date.now() + 60000)
    await query.refetch({ throwOnError: true })
    await refreshOrder()
  } })
  const pay = useMutation({ mutationFn: async () => {
    if (lock.current || !userId) return
    lock.current = true
    const epoch = session.epoch
    const assertIdentity = () => {
      if (!mounted.current || epoch !== sessionScope()) throw new Error('页面或登录身份已变化，请重新读取订单')
    }
    const assertForeground = () => {
      assertIdentity()
      if (!foreground.current) throw new Error('请返回订单页面查询原支付结果')
    }
    try {
      setNotice('')
      const latest = await privateRequest<ResponseModelPaymentStatusRead>(`/orders/${orderId}/payment-status`)
      assertIdentity()
      if (!latest.enabled) throw new Error('微信支付尚未开放')
      let attempt: PaymentAttemptRead | null | undefined = latest.attempt
      if (attempt?.status === 'succeeded') { await refreshOrder(); return }
      if (attempt?.status === 'unknown' || attempt?.status === 'created') throw new Error('支付结果确认中，请查询原交易')
      if (!attempt || attempt.status === 'closed' || attempt.status === 'unavailable') {
        const saved: unknown = Taro.getStorageSync(storageKey)
        let requestId: string | undefined
        if (saved) {
          if (!isPaymentRequestId(saved)) throw new Error('原支付请求记录无效，请联系支持核对')
          requestId = saved
          const previous = await privateRequest<ResponseModelPaymentStatusRead>(`/orders/${orderId}/payment-attempts/by-request/${requestId}`)
          assertIdentity()
          if (previous.attempt && !['closed', 'unavailable'].includes(previous.attempt.status)) attempt = previous.attempt
          else if (previous.attempt) requestId = undefined
        }
        if (!attempt || ['closed', 'unavailable'].includes(attempt.status)) {
          if (!requestId) {
            const ticket = await privateRequest<ResponseModelOperationIntentRead>('/payments/intent')
            assertIdentity()
            requestId = ticket.request_id
          }
          Taro.setStorageSync(storageKey, requestId)
          assertForeground()
          attempt = await privateRequest<ResponseModelPaymentAttemptRead>(`/orders/${orderId}/payment-attempts`, {
            method: 'POST', data: { request_id: requestId, channel: 'wechat' },
          })
          assertIdentity()
        }
      }
      if (!canInvokePayment(attempt) || !attempt?.payment_parameters) {
        setNotice(labels[attempt?.status ?? 'unknown'] ?? '请查询支付结果')
        return
      }
      assertForeground()
      try {
        await Taro.requestPayment(attempt.payment_parameters)
        assertIdentity()
        setNotice('正在向服务端确认付款结果')
      } catch {
        assertIdentity()
        setNotice('收银台已返回，请查询服务端支付结果')
      }
    } finally {
      lock.current = false
      if (mounted.current && foreground.current && epoch === sessionScope()) {
        setPollUntil(Date.now() + 60000)
        await query.refetch()
        await refreshOrder()
      }
    }
  } })
  const attempt = query.data?.attempt
  const blocked = !query.data?.enabled || query.isFetching || pay.isPending || refresh.isPending
    || ['created', 'unknown', 'succeeded'].includes(attempt?.status ?? '')
    || (attempt?.status === 'pending' && !attempt.payment_parameters)
  return <View className='surface'>
    <View className='section-title'>微信支付</View>
    {query.isPending && <QueryState title='正在读取支付状态' />}
    {(query.error || pay.error || refresh.error) && <QueryState title='支付结果未确认，请查询原交易' error={query.error ?? pay.error ?? refresh.error} />}
    {query.data && <View className='note'>{attempt ? labels[attempt.status] ?? '支付状态待核对' : query.data.enabled ? '由微信收银台完成付款' : '微信支付尚未开放'}</View>}
    {notice && <View className='note'>{notice}</View>}
    {query.data?.enabled && <Button block disabled={blocked} loading={pay.isPending} onClick={() => pay.mutate()}>{attempt?.status === 'pending' ? '继续付款' : '微信付款'}</Button>}
    <Button block fill='outline' disabled={pay.isPending || refresh.isPending} loading={refresh.isPending} onClick={() => refresh.mutate()}>查询付款与订单结果</Button>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>联系帮助支持</Button>
  </View>
}
