import { useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, View } from '@tarojs/components'
import { Icon } from '@/components/Icon'
import { AccountFrame } from '@/components/AccountFrame'
import { beginAuthentication } from '@/lib/auth-navigation'
import { useSession } from '@/lib/session'
import { AccountSummary, SignedInSummary } from './AccountSummary'
import { orderEntries, serviceEntries } from './entries'
import './account.scss'

export function AccountPage() {
  const session = useSession()
  const loggedIn = !!session.user?.phone_bound
  const [error, setError] = useState('')
  const navigating = useRef(false)

  async function open(target: string, access: 'phone' | 'public' | 'identity' = 'phone') {
    if (navigating.current) return
    navigating.current = true
    setError('')
    try {
      if (access === 'phone' && !loggedIn) await beginAuthentication(target)
      else if (access === 'identity' && !session.user) await beginAuthentication(target, false)
      else await Taro.navigateTo({ url: target })
    } catch { setError('页面打开失败，请点击原入口重试。') }
    finally { navigating.current = false }
  }

  return <AccountFrame title='我的' className='account-screen' bodyClassName='account-body'>
    {loggedIn
      ? <SignedInSummary key={session.epoch} open={(target) => { void open(target) }} />
      : <AccountSummary open={(target) => { void open(target) }} />}
    {(error || session.error) && <View className='account-feedback' role='alert'>{error || session.error}</View>}
    <View className='account-orders'>
      {orderEntries.map((entry) => <Button className='account-order' key={entry.label} onClick={() => { void open(entry.path) }}>
        <Icon className='account-order-icon' name={entry.icon} size={42} />
        <View>{entry.label}</View>
      </Button>)}
    </View>
    <View className='account-services'>
      <View className='account-section-title' role='heading'>我的服务</View>
      <View className='account-service-grid'>
        {serviceEntries.map((entry) => <Button className='account-service' key={entry.label} onClick={() => { void open(entry.path, entry.access) }}>
          <View className={`account-service-icon account-service-icon--${entry.tone}`}><Icon name={entry.icon} /></View>
          <View>{entry.label}</View>
        </Button>)}
      </View>
    </View>
    <View className='account-brand'><View /><View>拼捷商城</View><View /></View>
  </AccountFrame>
}
