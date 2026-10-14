import { useState } from 'react'
import type { PropsWithChildren } from 'react'
import Taro from '@tarojs/taro'
import { View } from '@tarojs/components'
import { Button } from './Button'
import { useSession } from '@/lib/session'
import { beginAuthentication } from '@/lib/auth-navigation'

export function AuthGate({ children, requirePhone = true }: PropsWithChildren<{ requirePhone?: boolean }>) {
  const session = useSession()
  const [error, setError] = useState('')
  if (session.user && (!requirePhone || session.user.phone_bound)) return <>{children}</>
  return <View className='page'><View className='surface auth-panel'>
    <View className='title'>{session.user ? '完善账户后继续' : '登录后继续'}</View>
    <View className='muted'>公开商品可直接浏览。此功能需要{requirePhone ? '微信身份和已验证手机号' : '微信身份'}，完成后返回当前页面。</View>
    {(error || session.error) && <View className='note'>{error || session.error}</View>}
    <Button block type='primary' loading={session.busy} disabled={session.busy} onClick={() => { void beginAuthentication(undefined, requirePhone).catch(() => setError('登录页面打开失败，请重试')) }}>{session.user ? '授权手机号并继续' : '微信登录'}</Button>
    <Button block fill='outline' onClick={() => { void Taro.switchTab({ url: '/pages/home/index' }) }}>继续浏览商品</Button>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>帮助与支持</Button>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/settings/index' }) }}>账户设置与隐私</Button>
  </View></View>
}
