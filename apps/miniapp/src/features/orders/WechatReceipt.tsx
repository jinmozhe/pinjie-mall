import { useRef, useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { ResponseModelPaymentStatusRead, ResponseModelWechatReceiptRead } from '@pinjie/api-client'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateRequest, sessionScope, useSession } from '@/lib/session'

export function WechatReceipt({ orderId }: { orderId: string }) {
  const session = useSession()
  const [notice, setNotice] = useState('')
  const lock = useRef(false)
  const capability = useQuery({
    queryKey: ['private', 'wechat-receipt-capability', session.epoch, orderId], gcTime: 0,
    queryFn: ({ signal }) => privateRequest<ResponseModelPaymentStatusRead>(`/orders/${orderId}/payment-status`, { signal }),
  })
  const verify = useMutation({ mutationFn: async () => {
    const result = await privateRequest<ResponseModelWechatReceiptRead>(`/orders/${orderId}/wechat-receipt`)
    if (session.epoch !== sessionScope()) return
    setNotice(result.confirmed ? '微信平台已确认收货' : '微信平台收货尚未确认，可稍后再次查询')
  } })
  useDidShow(() => {
    if (capability.data?.wechat_receipt_enabled && capability.data.wechat_transaction_id) verify.mutate()
  })
  const open = useMutation({ mutationFn: async () => {
    if (lock.current || !capability.data?.wechat_transaction_id) return
    lock.current = true
    try {
      await Taro.openBusinessView({
        businessType: 'weappOrderConfirm', extraData: { transaction_id: capability.data.wechat_transaction_id },
      })
      if (session.epoch === sessionScope()) await verify.mutateAsync()
    } finally { lock.current = false }
  } })
  if (capability.isError) return <QueryState title='微信平台订单入口读取失败' error={capability.error} retry={() => { void capability.refetch() }} />
  if (!capability.data?.wechat_receipt_enabled || !capability.data.wechat_transaction_id) return null
  return <View className='surface'>
    <View className='section-title'>微信平台订单</View>
    <View className='note'>微信平台收货结果与商城履约分别核对，关闭组件不会自动确认商城收货。</View>
    {notice && <View className='note'>{notice}</View>}
    {(open.error || verify.error) && <QueryState title='微信平台结果未确认' error={open.error ?? verify.error} />}
    <Button block disabled={open.isPending || verify.isPending} onClick={() => open.mutate()}>打开微信确认收货</Button>
    <Button block fill='outline' disabled={open.isPending || verify.isPending} onClick={() => verify.mutate()}>查询微信收货结果</Button>
  </View>
}
