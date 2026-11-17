import { useCallback, useEffect, useRef, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Image, Text, View } from '@tarojs/components'
import type { ResponseModelConsumerUserRead } from '@pinjie/api-client'
import { bindPhone, login, privateRequest, sessionScope, updateSessionUser, useSession } from '@/lib/session'
import { authNeedsPhone, cancelAuthentication, finishAuthentication } from '@/lib/auth-navigation'
import { LegalSheet } from './LegalSheet'
import type { LegalDocument } from './LegalSheet'
import shop from './assets/shop.svg'
import wechat from './assets/wechat.svg'
import './authentication.scss'

export function AuthenticationPage() {
  const session = useSession()
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [pendingPhoneUser, setPendingPhoneUser] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [document, setDocument] = useState<LegalDocument | null>(null)
  const guard = useRef(false)
  const navigating = useRef(false)
  const mounted = useRef(true)
  const phoneTapEpoch = useRef<number | null>(null)
  const profileAfterBinding = useRef<string | null>(null)
  const ready = !!session.user && (!authNeedsPhone() || session.user.phone_bound)
  const working = busy || session.busy
  const needsPhone = authNeedsPhone() && !session.user?.phone_bound
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; phoneTapEpoch.current = null }
  }, [])
  const continueToTarget = useCallback(async () => {
    if (navigating.current || !mounted.current || !session.user) return
    navigating.current = true
    try {
      if (session.user.phone_bound && profileAfterBinding.current === session.user.id) {
        await Taro.redirectTo({ url: '/subpackages/account/profile/index?onboarding=1' })
      } else await finishAuthentication()
    }
    catch (failure) { navigating.current = false; setError(failure instanceof Error ? failure.message : '页面返回失败，请重试') }
  }, [session.user])
  useEffect(() => {
    if (ready && !working && !document) void continueToTarget()
  }, [ready, working, document, continueToTarget])

  async function phone(code?: string) {
    const tappedEpoch = phoneTapEpoch.current
    phoneTapEpoch.current = null
    if (!mounted.current || guard.current || !consent || pendingPhoneUser) return
    if (!code) { setError('未取得手机号授权，您仍可暂不登录并浏览商品。'); return }
    if (tappedEpoch === null || tappedEpoch !== sessionScope()) { setError('会话已改变，请重新点击微信登录。'); return }
    guard.current = true; setBusy(true); setError('')
    try {
      const identity = await login()
      if (!mounted.current) return
      if (identity.epoch !== sessionScope()) throw new Error('会话已改变，请重新点击微信登录。')
      if (!identity.user.phone_bound) {
        profileAfterBinding.current = identity.user.id
        setPendingPhoneUser(identity.user.id)
        await bindPhone(code)
        setPendingPhoneUser(null)
      }
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : '绑定未完成，请先查询账户状态') }
    finally { guard.current = false; setBusy(false) }
  }

  async function check() {
    if (guard.current) return
    guard.current = true; setBusy(true); setError('')
    try {
      const identity = await login()
      if (!mounted.current) return
      if (identity.epoch !== sessionScope()) throw new Error('会话已改变，请重新查询。')
      if (identity.user.id !== pendingPhoneUser) {
        setPendingPhoneUser(null)
        throw new Error('账户已改变，原绑定结果需由原账户查询。当前账户请重新发起登录。')
      }
      const user = await privateRequest<ResponseModelConsumerUserRead>('/users/me')
      updateSessionUser(user, identity.epoch); setPendingPhoneUser(null)
      if (!user.phone_bound) setError('当前尚未绑定。上次请求仍可能完成；如需继续，请重新点击授权取得新凭证。')
    } catch (failure) { setError(failure instanceof Error ? failure.message : '查询失败，请重试') }
    finally { guard.current = false; setBusy(false) }
  }

  async function primaryAction() {
    if (guard.current || working) return
    if (ready) { await continueToTarget(); return }
    if (!consent) return
    if (pendingPhoneUser) { await check(); return }
    if (needsPhone) { phoneTapEpoch.current = sessionScope(); return }
    guard.current = true; setBusy(true); setError('')
    try { await login() }
    catch (failure) { setError(failure instanceof Error ? failure.message : '微信身份建立失败，请重试') }
    finally { guard.current = false; setBusy(false) }
  }

  async function skip() {
    if (guard.current || working || navigating.current) return
    phoneTapEpoch.current = null
    guard.current = true; setBusy(true); setError('')
    try { await cancelAuthentication() }
    catch (failure) { setError(failure instanceof Error ? failure.message : '返回失败，请重试') }
    finally { guard.current = false; setBusy(false) }
  }

  const buttonLabel = ready ? '继续' : pendingPhoneUser ? '查询绑定结果' : '微信登录'
  return <View className='auth-screen'>
    <View className='auth-decoration auth-decoration-left' />
    <View className='auth-decoration auth-decoration-right' />
    <View className='auth-orbit auth-orbit-left' />
    <View className='auth-orbit auth-orbit-right' />
    <View className='auth-hero'>
      <View className='auth-headline'><View>好物随心选</View><View className='auth-headline-accent'>分享好生活</View></View>
      <View className='auth-subtitle'>从日常所需，到心头所好</View>
      <Image className='auth-illustration' src={shop} mode='aspectFit' />
      <View className='auth-benefits'>商品选购 · 会员服务 · 推荐分享</View>
    </View>
    <View className='auth-actions'>
      <Button id='wechat-login' className='auth-login' disabled={working || (!ready && !consent)} loading={working}
        openType={consent && needsPhone && !pendingPhoneUser && !working ? 'getPhoneNumber|agreePrivacyAuthorization' : undefined}
        onClick={() => { void primaryAction() }}
        onGetPhoneNumber={(event) => { void phone(event.detail.code) }}>
        {!working && <Image className='auth-wechat-icon' src={wechat} mode='aspectFit' />}
        <Text>{buttonLabel}</Text>
      </Button>
      <Button className='auth-skip' disabled={working} onClick={() => { void skip() }}>暂不登录</Button>
      {(error || session.error) && <View className='auth-feedback' role='alert'>
        {error || session.error}
      </View>}
    </View>
    <View className='auth-consent-area'>
      <View className='auth-consent-row'>
        <Button className='auth-consent-toggle' ariaLabel={`${consent ? '已勾选' : '未勾选'}，我已阅读并同意用户协议与隐私条款`}
          disabled={working} onClick={() => setConsent(!consent)}>
          <View className={consent ? 'auth-checkbox auth-checkbox-checked' : 'auth-checkbox'}>{consent && <View className='auth-checkmark' />}</View>
        </Button>
        <View className='auth-consent-copy'>
          <Text onClick={() => { if (!working) setConsent(!consent) }}>我已阅读并同意</Text>
          <Text className='auth-legal-link' onClick={() => setDocument('agreement')}>《用户协议》</Text>
          <Text>与</Text>
          <Text className='auth-legal-link' onClick={() => setDocument('privacy')}>《隐私条款》</Text>
        </View>
      </View>
    </View>
    <LegalSheet document={document} onClose={() => setDocument(null)} />
  </View>
}
