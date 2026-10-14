import { useCallback, useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button as NativeButton, Checkbox, Text, View } from '@tarojs/components'
import type { ResponseModelConsumerUserRead } from '@pinjie/api-client'
import { Button } from '@/components/Button'
import { bindPhone, login, privateRequest, sessionScope, updateSessionUser, useSession } from '@/lib/session'
import { authNeedsPhone, cancelAuthentication, clearAuthIntent, finishAuthentication, profileGuideKey } from '@/lib/auth-navigation'

export function AuthenticationPage() {
  const session = useSession()
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [unknown, setUnknown] = useState(false)
  const [error, setError] = useState('')
  const guard = useRef(false)
  const navigating = useRef(false)
  const ready = !!session.user && (!authNeedsPhone() || session.user.phone_bound)
  const continueToTarget = useCallback(async () => {
    if (navigating.current || !session.user) return
    navigating.current = true
    try {
      if (authNeedsPhone() && (!session.user.display_name || !session.user.avatar)
        && Taro.getStorageSync(profileGuideKey(session.user.id)) !== true) {
        await Taro.redirectTo({ url: '/subpackages/account/profile/index?onboarding=1' })
      } else await finishAuthentication()
    } catch (failure) { navigating.current = false; setError(failure instanceof Error ? failure.message : '页面返回失败，请重试') }
  }, [session.user])
  useEffect(() => { if (ready && !busy) void continueToTarget() }, [ready, busy, continueToTarget])
  async function phone(code?: string) {
    if (guard.current) return
    if (!code) { setError('未取得手机号授权，可继续浏览'); return }
    guard.current = true; setBusy(true); setError(''); setUnknown(true)
    try { await bindPhone(code); setUnknown(false) }
    catch (failure) { setError(failure instanceof Error ? failure.message : '绑定未完成，请先查询账户状态') }
    finally { guard.current = false; setBusy(false) }
  }
  async function check() {
    if (guard.current) return
    guard.current = true; setBusy(true); setError('')
    const epoch = sessionScope()
    try {
      const user = await privateRequest<ResponseModelConsumerUserRead>('/users/me')
      updateSessionUser(user, epoch); setUnknown(false)
      if (!user.phone_bound) setError('当前尚未绑定。上次请求仍可能完成；如需继续，请重新点击授权取得新凭证。')
    } catch (failure) { setError(failure instanceof Error ? failure.message : '查询失败') }
    finally { guard.current = false; setBusy(false) }
  }
  return <View className='page account-page'><View className='surface auth-panel'>
    <View className='title'>{ready ? '账户已就绪' : session.user ? '绑定手机号' : '登录拼捷商城'}</View>
    {!session.user && <>
      <View className='muted'>微信用于识别商城账户，首次使用将自动创建账户。用户名、手机号和昵称分别保存。</View>
      <View className='consent' onClick={() => setConsent(!consent)}><Checkbox value='privacy' checked={consent} color='#B42318' /><Text>我已阅读并同意</Text><Text className='link' onClick={(event) => { event.stopPropagation(); void Taro.navigateTo({ url: '/subpackages/account/privacy/index' }) }}>隐私说明</Text></View>
      <Button block loading={session.busy} disabled={!consent || session.busy} onClick={() => { void login() }}>微信登录并继续</Button>
    </>}
    {session.user && !ready && <>
      <View className='muted'>微信身份已确认。手机号用于完善商城账户及购物服务，成功绑定后日常使用无需重复授权。</View>
      <NativeButton className='native-account-button' openType='getPhoneNumber' disabled={busy || unknown} loading={busy}
        onGetPhoneNumber={(event) => { void phone(event.detail.code) }}>授权手机号并继续</NativeButton>
      {unknown && <View className='note'>绑定结果尚未确认，请先查询，不要重复提交原凭证。</View>}
      <Button block fill='outline' disabled={busy} onClick={() => { void check() }}>查询手机号绑定状态</Button>
    </>}
    {(error || session.error) && <View className='note'>{error || session.error}</View>}
    {ready && <Button block disabled={busy} onClick={() => { void continueToTarget() }}>继续</Button>}
    <Button block fill='outline' disabled={busy || session.busy} onClick={() => { void cancelAuthentication().catch(() => setError('返回失败，请使用首页入口')) }}>取消并返回</Button>
    <Button block fill='outline' disabled={busy || session.busy} onClick={() => { clearAuthIntent(); void Taro.switchTab({ url: '/pages/home/index' }) }}>继续浏览首页</Button>
  </View></View>
}
