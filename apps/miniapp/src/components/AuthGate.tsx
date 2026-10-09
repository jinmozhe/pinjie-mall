import { useState } from 'react'
import type { PropsWithChildren } from 'react'
import Taro from '@tarojs/taro'
import { Checkbox, Text, View } from '@tarojs/components'
import { Button } from './Button'
import { login, useSession } from '@/lib/session'

export function AuthGate({ children }: PropsWithChildren) {
  const session = useSession()
  const [consent, setConsent] = useState(false)
  if (session.user) return <>{children}</>
  return <View className='page'><View className='surface auth-panel'>
    <View className='title'>登录拼捷商城</View>
    <View className='muted'>登录后使用购物车、收货地址和订单服务。微信身份仅用于识别您的商城账户。</View>
    <View className='consent' onClick={() => setConsent(!consent)}><Checkbox value='privacy' checked={consent} color='#B42318' /><Text>我已阅读并同意</Text><Text className='link' onClick={(event) => { event.stopPropagation(); void Taro.navigateTo({ url: '/subpackages/account/privacy/index' }) }}>隐私说明</Text></View>
    {session.error && <View className='note'>{session.error}</View>}
    <Button block type='primary' loading={session.busy} disabled={!consent || session.busy} onClick={() => { void login() }}>微信登录</Button>
    <Button block fill='outline' onClick={() => { void Taro.switchTab({ url: '/pages/home/index' }) }}>继续浏览商品</Button>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>帮助与支持</Button>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/settings/index' }) }}>账户设置与隐私</Button>
  </View></View>
}
