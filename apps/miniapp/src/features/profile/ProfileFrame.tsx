import { useRef, useState } from 'react'
import type { PropsWithChildren } from 'react'
import Taro, { useDidShow, useResize, useRouter } from '@tarojs/taro'
import { Button, Image, ScrollView, View } from '@tarojs/components'
import { QueryState } from '@/components/QueryState'
import { finishAuthentication } from '@/lib/auth-navigation'
import background from './assets/background.svg'

type Layout = { top: number; height: number; side: number }
function readLayout(): { layout: Layout | null; error: string } {
  try {
    const { statusBarHeight, windowWidth, windowHeight } = Taro.getWindowInfo()
    const menu = Taro.getMenuButtonBoundingClientRect()
    const values = [statusBarHeight, windowWidth, windowHeight, menu.top, menu.height, menu.left, menu.right]
    if (typeof statusBarHeight !== 'number' || !values.every(Number.isFinite) || statusBarHeight < 0 || windowWidth <= 0 || windowHeight <= 0
      || menu.height <= 0 || menu.top < statusBarHeight || menu.left <= 0 || menu.right > windowWidth || menu.right <= menu.left) {
      throw new Error('Invalid navigation bounds')
    }
    const height = Math.max(44, menu.height + 2 * (menu.top - statusBarHeight))
    const side = Math.max(44, windowWidth - menu.left + 8)
    if (side * 2 >= windowWidth || statusBarHeight + height >= windowHeight) throw new Error('Insufficient viewport')
    return { layout: { top: statusBarHeight, height, side }, error: '' }
  } catch { return { layout: null, error: '页面布局加载失败，请重试。' } }
}

export function ProfileFrame({ children }: PropsWithChildren) {
  const onboarding = useRouter().params.onboarding === '1'
  const [{ layout, error }, setLayout] = useState(readLayout)
  const [navigationError, setNavigationError] = useState('')
  const [leaving, setLeaving] = useState(false)
  const guard = useRef(false)
  useDidShow(() => setLayout(readLayout()))
  useResize(() => setLayout(readLayout()))
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
      <QueryState title='页面暂时无法显示' detail={error} retry={() => setLayout(readLayout())} />
      {navigationError && <View role='alert'>{navigationError}</View>}
      <Button className='profile-text-action' disabled={leaving} onClick={() => { void back() }}>返回上一页</Button>
    </View>}
  </View>
}
