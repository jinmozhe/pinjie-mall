import type { PropsWithChildren } from 'react'
import { Button, ScrollView, View } from '@tarojs/components'
import { useNavigationLayout } from '@/lib/use-navigation-layout'
import { AccountBackground } from './AccountBackground'
import { QueryState } from './QueryState'

type Props = PropsWithChildren<{
  title: string
  className?: string
  bodyClassName?: string
  onBack?: () => void
  backDisabled?: boolean
  navigationError?: string
}>

export function AccountFrame({ title, className = '', bodyClassName = '', onBack, backDisabled, navigationError, children }: Props) {
  const { layout, error, refresh } = useNavigationLayout()
  return <View className={`account-frame ${className}`}>
    <AccountBackground />
    {layout ? <>
      <View className='account-frame-header' style={{ paddingTop: `${layout.top}px` }}>
        <View className='account-frame-header-row' style={{ height: `${layout.height}px`, paddingLeft: `${layout.side}px`, paddingRight: `${layout.side}px` }}>
          {onBack && <Button className='account-frame-back' ariaLabel='返回上一页' disabled={backDisabled} onClick={onBack}><View /></Button>}
          <View className='account-frame-title' role='heading'>{title}</View>
        </View>
      </View>
      <ScrollView className='account-frame-scroll' scrollY enhanced showScrollbar={false}>
        <View className={`account-frame-body ${bodyClassName}`}>
          {navigationError && <View className='account-frame-error' role='alert'>{navigationError}</View>}
          {children}
        </View>
      </ScrollView>
    </> : <View className='account-frame-layout-error'>
      <QueryState title='页面暂时无法显示' detail={error} retry={refresh} />
      {navigationError && <View role='alert'>{navigationError}</View>}
      {onBack && <Button className='account-frame-retry-back' disabled={backDisabled} onClick={onBack}>返回上一页</Button>}
    </View>}
  </View>
}
