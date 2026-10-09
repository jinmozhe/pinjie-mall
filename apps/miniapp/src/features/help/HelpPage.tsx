import { useState } from 'react'
import Taro from '@tarojs/taro'
import { View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import type { ResponseModelMiniappHelpRead } from '@pinjie/api-client'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { getPublic } from '@/lib/api'

const topics = [
  ['订单和支付', '订单状态以商城服务端为准。微信支付目前尚未开放；零金额订单由服务端确认成交。到期提示不会在客户端取消订单。'],
  ['实物配送与虚拟交付', '实物发货后可在订单详情查看承运人与运单号，收到全部商品后主动确认收货。当前不提供实时物流轨迹。虚拟商品的交付信息仅向订单本人显示。'],
  ['整单退款', '仅已成交且实物未发货、虚拟未交付订单可申请，覆盖全部商品与原运费。未接单自动审核，已接单人工审核。已发货或已交付订单不开放本期售后。'],
  ['审核与资金退回', '审核通过仅表示审核事实。渠道处理中、异常或结果未知时不能确认到账，请继续查询或联系运营。零金额售后无资金退回。'],
  ['申请超时如何处理', '请从订单详情打开退款资格与申请恢复，查询原请求号。查询未找到后可主动使用原请求号和原原因重试。查询失败时请保留记录，勿创建新的退款请求。'],
  ['评价', '仅本人已交付明细可评价一次。提交超时后查询已有评价，不自动重复提交。请勿在公开评价中填写个人信息。'],
]
export function HelpPage() {
  const [open, setOpen] = useState<number | null>(null)
  const [contactError, setContactError] = useState('')
  const query = useQuery({ queryKey: ['help'], gcTime: 0, queryFn: ({ signal }) => getPublic<ResponseModelMiniappHelpRead>('/miniapp/help', signal) })
  async function contact(kind: 'phone' | 'email') {
    setContactError('')
    try {
      if (kind === 'phone' && query.data?.phone) await Taro.makePhoneCall({ phoneNumber: query.data.phone })
      if (kind === 'email' && query.data?.email) await Taro.setClipboardData({ data: query.data.email })
    } catch { setContactError('联系操作未完成，可稍后重试或手动使用下方联系方式') }
  }
  return <View className='page'><View className='title'>帮助与支持</View><View className='surface'><View className='section-title'>常见问题</View>{topics.map(([title, body], index) => <View className='order-line' key={title}><Button block fill='outline' onClick={() => setOpen(open === index ? null : index)}>{title} {open === index ? '收起' : '展开'}</Button>{open === index && <View className='help-answer'>{body}</View>}</View>)}</View><View className='surface'><View className='section-title'>联系运营</View>{query.isPending && <QueryState title='正在读取联系方式' />}{query.isError && <QueryState title='联系方式读取失败' error={query.error} retry={() => { void query.refetch() }} />}{query.data && !query.isError && <>{!query.data.phone && !query.data.email && <View className='note'>运营联系方式尚未配置，暂时无法提供联系渠道。</View>}{query.data.phone && <><View className='wrap'>电话：{query.data.phone}</View><Button block fill='outline' onClick={() => { void contact('phone') }}>拨打电话</Button></>}{query.data.email && <><View className='wrap'>邮箱：{query.data.email}</View><Button block fill='outline' onClick={() => { void contact('email') }}>复制邮箱</Button></>}<View className='muted'>求助时可提供订单号和服务请求号，请勿发送登录凭据、支付密钥或完整个人资料。</View></>}{contactError && <View className='note'>{contactError}</View>}</View><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/privacy/index' }) }}>隐私说明</Button></View>
}
