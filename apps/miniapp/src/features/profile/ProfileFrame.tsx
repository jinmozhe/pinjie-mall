import { useRef, useState } from 'react'
import type { PropsWithChildren } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { Button, Image, ScrollView, View } from '@tarojs/components'
import { QueryState } from '@/components/QueryState'
import { finishAuthentication } from '@/lib/auth-navigation'
import { useNavigationLayout } from '@/lib/use-navigation-layout'
import background from './assets/background.svg'

export function ProfileFrame({ children }: PropsWithChildren) {
  const onboarding = useRouter().params.onboarding === '1'
  const { layout, error, refresh } = useNavigationLayout()
  const [navigationError, setNavigationError] = useState('')
  const [leaving, setLeaving] = useState(false)
  const guard = useRef(false)
  async function back() {
    if (guard.current) return
    guard.current = true; setLeaving(true); setNavigationError('')
    try {
      if (onboarding) await finishAuthentication({ fromProfile: true })
      else if (Taro.getCurrentPages().length > 1) await Taro.navigateBack()
      else await Taro.switchTab({ url: '/pages/account/index' })
    } catch { setNavigationError('返回失败，请再试一次。') }
    finally { guard.current = false; setLeaving(false) }
  }
  return <View className='profile-screen'>
    <Image className='profile-background' src={background} mode='aspectFill' />
    {layout ? <>
      <View className='profile-header' style={{ paddingTop: `${layout.top}px` }}>
        <View className='profile-header-row' style={{ height: `${layout.height}px`, paddingLeft: `${layout.side}px`, paddingRight: `${layout.side}px` }}>
          <Button className='profile-back' ariaLabel='返回上一页' disabled={leaving} onClick={() => { void back() }}><View /></Button>
          <View className='profile-header-title' role='heading'>个人资料</View>
        </View>
      </View>
      <ScrollView className='profile-scroll' scrollY enhanced showScrollbar={false}>
        <View className='profile-body'>
          {navigationError && <View className='profile-navigation-error' role='alert'>{navigationError}</View>}
          {children}
        </View>
      </ScrollView>
    </> : <View className='profile-layout-error'>
      <QueryState title='页面暂时无法显示' detail={error} retry={refresh} />
      {navigationError && <View role='alert'>{navigationError}</View>}
      <Button className='profile-text-action' disabled={leaving} onClick={() => { void back() }}>返回上一页</Button>
    </View>}
  </View>
}
