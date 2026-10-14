import Taro, { useDidShow } from '@tarojs/taro'
import { View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import type { ResponseModelConsumerUserRead } from '@pinjie/api-client'
import { AccountAvatar } from '@/components/AccountAvatar'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { logout, privateRequest, sessionScope, useSession } from '@/lib/session'
import { beginAuthentication } from '@/lib/auth-navigation'
import { useState } from 'react'

function Content() {
  const session = useSession()
  const profile = useQuery({ queryKey: ['private', 'me', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerUserRead>('/users/me', { signal }) })
  useDidShow(() => { void profile.refetch() })
  return <View className='page'>
    <View className='surface'><AccountAvatar url={profile.data?.avatar} /><View className='title wrap'>{profile.data?.display_name || '微信商城用户'}</View><View className='muted'>欢迎来到拼捷商城</View>{profile.isPending && <QueryState title='正在读取账户信息' />}{profile.isError && <QueryState title='账户信息读取失败' error={profile.error} retry={() => { void profile.refetch() }} />}<Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/profile/index' }) }}>编辑个人资料</Button></View>
    <View className='surface menu-list'><View className='touch trade-row spread' onClick={() => { void Taro.navigateTo({ url: '/subpackages/trade/orders/index' }) }}>我的订单 <View>›</View></View><View className='category-strip'>{[['待付款', 'pending_payment'], ['已付款', 'paid'], ['已取消', 'cancelled']].map(([label, status]) => <Button fill='outline' key={status} onClick={() => { void Taro.navigateTo({ url: `/subpackages/trade/orders/index?status=${status}` }) }}>{label}</Button>)}</View><View className='touch trade-row spread' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/addresses/index' }) }}>收货地址 <View>›</View></View><View className='touch trade-row spread' onClick={() => { void Taro.navigateTo({ url: '/subpackages/trade/checkout/index' }) }}>继续未完成结算 <View>›</View></View><View className='touch trade-row spread' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/privacy/index' }) }}>隐私说明 <View>›</View></View></View>
    <View className='surface'><View className='section-title'>履约与售后</View><View className='category-strip'>{[['待发货', 'awaiting_shipment'], ['待交付', 'awaiting_delivery'], ['待收货', 'shipped'], ['已完成', 'delivered']].map(([label, status]) => <Button fill='outline' key={status} onClick={() => { void Taro.navigateTo({ url: `/subpackages/trade/orders/index?status=${status}` }) }}>{label}</Button>)}</View><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/refunds/index' }) }}>售后记录</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>帮助与支持</Button></View>
    <View className='surface'><View className='section-title'>会员与钱包</View>{[['会员中心', 'membership'], ['推荐与分享', 'referral'], ['我的积分', 'points'], ['双轨钱包与流水', 'wallets'], ['佣金记录', 'commissions'], ['历史提现记录', 'withdrawals']].map(([label, path]) => <View className='touch trade-row spread' key={path} onClick={() => { void Taro.navigateTo({ url: `/subpackages/finance/${path}/index` }) }}>{label}<View>›</View></View>)}</View>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/settings/index' }) }}>账户设置与安全</Button>
    <View className='note'>微信支付、新提现、充值与消费钱包抵扣尚未开放。金额与执行结果以服务端事实为准。</View>
    <Button block fill='outline' onClick={() => { void Taro.showModal({ title: '退出登录', content: '退出后清除本机内存会话，下次需主动登录。' }).then((answer) => { if (answer.confirm && session.epoch === sessionScope()) void logout() }) }}>退出登录</Button>
  </View>
}
export function AccountPage() {
  const session = useSession()
  const [error, setError] = useState('')
  if (session.user?.phone_bound) return <Content key={session.epoch} />
  async function open(target: string) {
    try { await beginAuthentication(target) } catch { setError('页面打开失败，请重试') }
  }
  return <View className='page account-page'>
    <View className='surface'><AccountAvatar url={null} /><View className='title'>欢迎来到拼捷商城</View>
      <View className='muted'>{session.user ? '微信身份已识别，按需完善手机号后使用账户功能。' : '商品可直接浏览，使用账户功能时再登录。'}</View>
      <Button block loading={session.busy} disabled={session.busy} onClick={() => { void open('/pages/account/index') }}>{session.user ? '授权手机号，完善账户' : '微信登录'}</Button>
    </View>
    <View className='surface menu-list'>{[
      ['我的订单', '/subpackages/trade/orders/index'], ['收货地址', '/subpackages/account/addresses/index'],
      ['继续未完成结算', '/subpackages/trade/checkout/index'], ['售后记录', '/subpackages/service/refunds/index'],
      ['会员中心', '/subpackages/finance/membership/index'], ['推荐与分享', '/subpackages/finance/referral/index'],
      ['我的积分', '/subpackages/finance/points/index'], ['双轨钱包与流水', '/subpackages/finance/wallets/index'],
      ['佣金记录', '/subpackages/finance/commissions/index'], ['历史提现记录', '/subpackages/finance/withdrawals/index'],
    ].map(([label, path]) => <View className='touch trade-row spread' key={path} onClick={() => { void open(path) }}>{label}<View>›</View></View>)}</View>
    {(error || session.error) && <View className='note'>{error || session.error}</View>}
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/settings/index' }) }}>账户设置与隐私</Button>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>帮助与支持</Button>
  </View>
}
