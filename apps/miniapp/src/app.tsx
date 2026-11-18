import { useEffect, useState } from 'react'
import type { PropsWithChildren } from 'react'
import Taro, { useDidHide, useDidShow, useLaunch } from '@tarojs/taro'
import { View } from '@tarojs/components'
import { configure } from '@nutui/icons-react-taro/dist/es/icons/configure'
import { focusManager, onlineManager, QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/query'
import { restoreSession } from './lib/session'
import { startRouteTrace, stopRouteTrace } from './platform/route-trace'
import { CartBadge } from './features/cart'
import './styles/app.scss'
import '@nutui/icons-react-taro/dist/style_icon.css'

// The icon package defaults to the unsupported HTML tag "i" on weapp.
configure({ tag: 'view' })

export default function App({ children }: PropsWithChildren) {
  const [networkNote, setNetworkNote] = useState('')
  useLaunch((options) => {
    if (__ROUTE_TRACE_ENABLED__) startRouteTrace(options.path)
  })
  useDidShow(() => { focusManager.setFocused(true) })
  useDidHide(() => { focusManager.setFocused(false) })
  useEffect(() => {
    void restoreSession()
    let live = true
    let revision = 0
    function update(connected: boolean) {
      onlineManager.setOnline(connected)
      setNetworkNote(connected ? '' : '网络不可用，连接恢复后继续加载')
    }
    const listener: Parameters<typeof Taro.onNetworkStatusChange>[0] = (event) => {
      revision += 1
      update(event.isConnected)
    }
    Taro.onNetworkStatusChange(listener)
    const initialRevision = revision
    void Taro.getNetworkType().then((result) => {
      if (live && revision === initialRevision) update(result.networkType !== 'none')
    }, () => {
      if (live && revision === initialRevision) {
        onlineManager.setOnline(false)
        setNetworkNote('无法获取网络状态，请检查微信网络权限并重新打开小程序')
      }
    })
    return () => {
      live = false
      Taro.offNetworkStatusChange(listener)
      if (__ROUTE_TRACE_ENABLED__) stopRouteTrace()
    }
  }, [])
  return <QueryClientProvider client={queryClient}><CartBadge />{networkNote && <View className='network-note'>{networkNote}</View>}{children}</QueryClientProvider>
}
