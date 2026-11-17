import { useRef, useState } from 'react'
import type { PropsWithChildren } from 'react'
import Taro, { useRouter } from '@tarojs/taro'
import { AccountFrame } from '@/components/AccountFrame'
import { finishAuthentication } from '@/lib/auth-navigation'

export function ProfileFrame({ children }: PropsWithChildren) {
  const onboarding = useRouter().params.onboarding === '1'
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
  return <AccountFrame title='个人资料' className='profile-screen' onBack={() => { void back() }} backDisabled={leaving} navigationError={navigationError}>
    {children}
  </AccountFrame>
}
