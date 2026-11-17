import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useDidShow } from '@tarojs/taro'
import { Button, Image, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import type { ConsumerUserRead, ResponseModelConsumerMemberRead, ResponseModelConsumerPointsRead, ResponseModelConsumerUserRead, ResponseModelListConsumerWalletRead } from '@pinjie/api-client'
import { QueryState } from '@/components/QueryState'
import { privateRequest, useSession } from '@/lib/session'
import { assetUrl } from '@/platform/media'

const accountPath = '/pages/account/index'
const profilePath = '/subpackages/account/profile/index'
const walletsPath = '/subpackages/finance/wallets/index'
const pointsPath = '/subpackages/finance/points/index'
type Open = (target: string) => void
type Asset = { label: string; value: string; path: string }

function Avatar({ url, open }: { url?: string | null; open: () => void }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [url])
  let source = ''
  let invalid = false
  if (url) { try { source = assetUrl(url) } catch { invalid = true } }
  return <View className='account-portrait'>
    <Button className='account-portrait-button' ariaLabel='头像' onClick={open}>
      {source && !failed ? <Image src={source} mode='aspectFill' onError={() => setFailed(true)} /> : <View className='account-portrait-placeholder'><View /><View /></View>}
    </Button>
    {invalid && <View className='account-portrait-error'>头像来源未获准入</View>}
    {failed && <Button className='account-portrait-retry' onClick={() => setFailed(false)}>头像加载失败，重试</Button>}
  </View>
}

export function AccountSummary({ open, user, assets, children }: { open: Open; user?: ConsumerUserRead | null; assets?: Asset[]; children?: ReactNode }) {
  const loggedIn = !!user
  const target = loggedIn ? profilePath : accountPath
  const values = assets ?? [
    { label: '佣金钱包', value: '•••', path: walletsPath },
    { label: '消费钱包', value: '•••', path: walletsPath },
    { label: '我的积分', value: '•••', path: pointsPath },
  ]
  return <View className='account-summary'>
    <View className='account-identity'>
      <Avatar url={user?.avatar} open={() => open(target)} />
      <Button className='account-identity-button' onClick={() => open(target)}>
        <View className='account-name'>{loggedIn ? user.display_name || '微信商城用户' : '未登录'}</View>
        <View className='account-welcome'>欢迎来到拼捷商城</View>
        <View className='account-chevron' />
      </Button>
    </View>
    <View className='account-assets'>
      {values.map((asset) => <Button className='account-asset' key={asset.label} onClick={() => open(asset.path)}>
        <View className={`account-asset-value${loggedIn ? '' : ' account-asset-value--hidden'}`}>{asset.value}</View>
        <View className='account-asset-label'>{asset.label}</View>
      </Button>)}
    </View>
    {!loggedIn && <View className='account-login-strip'>
      <View>登录后查看订单与资产</View>
      <Button className='account-login' onClick={() => open(accountPath)}><View>去登录</View></Button>
    </View>}
    {children}
  </View>
}

export function SignedInSummary({ open }: { open: Open }) {
  const session = useSession()
  const profile = useQuery({ queryKey: ['private', 'me', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerUserRead>('/users/me', { signal }) })
  const membership = useQuery({ queryKey: ['private', 'membership', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerMemberRead>('/distribution/me/profile', { signal }) })
  const walletEnabled = !!membership.data && !membership.isError && membership.data.state !== 'not_opened'
  const wallets = useQuery({ queryKey: ['private', 'wallets', session.epoch], enabled: walletEnabled, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelListConsumerWalletRead>('/distribution/me/wallets', { signal }) })
  const points = useQuery({ queryKey: ['private', 'points', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerPointsRead>('/users/me/points', { signal }) })
  useDidShow(() => {
    void profile.refetch(); void membership.refetch(); void points.refetch()
    if (walletEnabled) void wallets.refetch()
  })

  function walletValue(type: 'commission' | 'consumption') {
    if (membership.isError) return '读取失败'
    if (membership.isPending) return '加载中'
    if (membership.data.state === 'not_opened') return '账户异常'
    if (wallets.isError) return '读取失败'
    if (wallets.isPending) return '加载中'
    const wallet = wallets.data.find((entry) => entry.wallet_type === type)
    return wallet ? `¥${wallet.available_amount}` : '账户缺失'
  }
  const pointsValue = points.isError ? '读取失败' : points.isPending ? '加载中'
    : points.data.state === 'not_opened' ? '账户异常' : points.data.account?.available_points ?? '账户缺失'
  const assets = [
    { label: '佣金钱包', value: walletValue('commission'), path: walletsPath },
    { label: '消费钱包', value: walletValue('consumption'), path: walletsPath },
    { label: '我的积分', value: pointsValue, path: pointsPath },
  ]
  return <AccountSummary open={open} user={profile.data ?? session.user} assets={assets}>
    {profile.isPending && <View className='account-summary-notice'>正在更新账户资料</View>}
    {profile.isError && <QueryState title='账户信息读取失败' error={profile.error} retry={() => { void profile.refetch() }} />}
    {membership.isError && <QueryState title='会员状态读取失败' error={membership.error} retry={() => { void membership.refetch() }} />}
    {!membership.isError && !points.isError && (membership.data?.state === 'not_opened' || points.data?.state === 'not_opened') && <View className='account-summary-notice'>账户信息暂不可用，请重新登录；若仍异常，请联系帮助与支持。</View>}
    {walletEnabled && wallets.isError && <QueryState title='钱包读取失败' error={wallets.error} retry={() => { void wallets.refetch() }} />}
    {points.isError && <QueryState title='积分读取失败' error={points.error} retry={() => { void points.refetch() }} />}
  </AccountSummary>
}
