import { useRef, useState } from 'react'
import Taro, { useDidShow, useRouter, useShareAppMessage } from '@tarojs/taro'
import { Button as NativeButton, Input, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { ResponseModelConsumerReferralRead } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { ApiError } from '@/lib/api'
import { privateRequest, sessionScope, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'
import { invitationCode, referralPath } from './domain'
import { clearIntent, loadIntent, saveIntent } from './intent'

function Content({ invite }: { invite: string | null }) {
  const session = useSession()
  const userId = session.user!.id
  const [recovery] = useState(() => {
    try { return { code: loadIntent(userId), error: '' } }
    catch (error) { return { code: null, error: error instanceof Error ? error.message : '无法读取绑定恢复记录，请联系支持' } }
  })
  const [pending, setPending] = useState(recovery.code)
  const [input, setInput] = useState(recovery.code ?? invite ?? '')
  const [notice, setNotice] = useState('')
  const sending = useRef(false)
  const key = ['private', 'referral', session.epoch]
  const query = useQuery({ queryKey: key, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerReferralRead>('/distribution/me/referrer', { signal }) })
  useDidShow(() => { void query.refetch() })
  const code = invitationCode(input)
  const readonly = !!recovery.error || !!pending

  async function accept(result: ResponseModelConsumerReferralRead['data'], original: string) {
    await queryClient.cancelQueries({ queryKey: key })
    if (session.epoch !== sessionScope()) throw new Error('会话已改变，请重新读取推荐关系')
    queryClient.setQueryData(key, { ...result, matches_invitation: null })
    if (result.state === 'bound') {
      if (result.matches_invitation === null) throw new Error('尚未取得原码匹配事实，请继续查询')
      clearIntent(userId)
      setPending(null)
      setNotice(result.matches_invitation ? `服务端已确认绑定推荐码 ${original}。` : '当前已绑定其他推荐关系，原码未匹配，不能换绑。')
      void queryClient.invalidateQueries({ queryKey: ['private', 'membership', session.epoch] })
      void queryClient.invalidateQueries({ queryKey: ['private', 'wallets', session.epoch] })
    } else {
      setNotice('当前查询尚未确认绑定，在途请求仍可能完成。请继续查询，或主动使用原码恢复。')
    }
  }
  const bind = useMutation({ mutationFn: async (restore: boolean) => {
    if (sending.current || recovery.error || query.isError || !query.data || query.data.state === 'bound') throw new Error('请先读取有效的推荐关系')
    const original = restore ? pending : code
    if (!original || !restore && pending || original === query.data.invitation_code) throw new Error('请输入有效的他人推荐码，并先确认上次绑定结果')
    sending.current = true
    lookup.reset()
    copy.reset()
    try {
      const answer = await Taro.showModal({ title: restore ? '恢复原码绑定' : '确认绑定推荐人', content: `当前商城账户：${session.user?.display_name || '微信商城用户'}。推荐码：${original}。关系只能首次绑定，确认后不能更换；绑定不承诺积分或佣金奖励。` })
      if (!answer.confirm || session.epoch !== sessionScope()) return
      // Persist before sending; failure to save prevents the write.
      saveIntent(userId, original)
      setPending(original)
      setNotice('正在确认推荐关系，请勿换码重复提交。')
      try {
        const result = await privateRequest<ResponseModelConsumerReferralRead>('/distribution/me/referrer', { method: 'POST', data: { invitation_code: original } })
        await accept(result, original)
      } catch (error) {
        // Only a definitive rejection of a NEW write releases the intent. A prior unknown write may still finish.
        if (!restore && session.epoch === sessionScope() && error instanceof ApiError && error.kind === 'http' && (error.status === 422 || [404, 409].includes(error.status) && error.code === 'DISTRIBUTION_REFERRAL_REJECTED')) {
          clearIntent(userId)
          setPending(null)
          setNotice('服务端已拒绝本次绑定，请检查邀请码或查询已有关系。')
          void query.refetch()
        }
        throw error
      }
    } finally { sending.current = false }
  } })
  const lookup = useMutation({ mutationFn: async () => {
    bind.reset()
    copy.reset()
    const original = pending ?? code
    const result = await privateRequest<ResponseModelConsumerReferralRead>(`/distribution/me/referrer${original ? `?invitation_code=${encodeURIComponent(original)}` : ''}`)
    if (original) await accept(result, original)
    else {
      await queryClient.cancelQueries({ queryKey: key })
      if (session.epoch !== sessionScope()) return
      queryClient.setQueryData(key, result)
      setNotice('已读取当前关系。')
    }
  } })
  const copy = useMutation({ mutationFn: async () => {
    bind.reset()
    lookup.reset()
    const own = query.data?.invitation_code
    if (!own || query.isError) throw new Error('请先读取本人邀请码')
    await Taro.setClipboardData({ data: own })
    if (session.epoch === sessionScope()) setNotice('本人邀请码已复制。复制不代表邀请已生效。')
  } })
  const busy = bind.isPending || lookup.isPending || copy.isPending
  return <View className='page account-page'>
    <View className='title'>推荐与分享</View>
    {query.isPending && <QueryState title='正在读取本人推荐关系' />}
    {query.isError && <QueryState title='推荐关系读取失败' error={query.error} retry={() => { void query.refetch() }} />}
    {query.data && !query.isError && <>
      <View className='surface'><View className='section-title'>我的邀请码</View>
        {query.data.invitation_code ? <><View className='referral-code wrap'>{query.data.invitation_code}</View><Button block fill='outline' disabled={busy} onClick={() => copy.mutate()}>复制本人邀请码</Button><NativeButton className='share-button' openType='share' disabled={busy}>分享商城给微信好友</NativeButton><View className='muted'>分享仅传递本人邀请码。对方需登录并主动确认；分享次数不代表有效邀请或收益。</View></> : <><View className='muted'>尚未开通会员分销档案，暂未生成本人邀请码。</View><Button block onClick={() => { void Taro.navigateTo({ url: '/subpackages/finance/membership/index' }) }}>前往会员中心开通</Button></>}
      </View>
      <View className='surface profile-form'><View className='section-title'>我的推荐关系</View>
        {query.data.state === 'bound' ? <><View>已绑定，不能更换推荐人</View><View className='muted'>绑定时间：{query.data.bound_at ? new Date(query.data.bound_at).toLocaleString() : '尚无记录'}</View></> : <><View className='field-label'>推荐人的邀请码</View><Input value={input} maxlength={32} disabled={busy || readonly} placeholder='请输入 8 至 16 位字母或数字' onInput={(event) => { setInput(event.detail.value); setNotice('') }} /><View className='muted'>关系仅首次绑定；服务端拒绝自邀和循环。绑定将按既有规则创建本人分销档案及双轨钱包。</View>{input && !code && <View className='note'>邀请码格式无效，请检查原始邀请码，勿粘贴网址。</View>}<Button block disabled={busy || readonly || !code || code === query.data.invitation_code} loading={bind.isPending} onClick={() => bind.mutate(false)}>确认首次绑定</Button></>}
      </View>
    </>}
    {pending && <View className='note wrap'>原码 {pending} 的结果尚待确认。先查询匹配事实；未确认前保留原码，无法换码重试。{query.data?.state !== 'bound' && <Button block fill='outline' disabled={busy || query.isError || !query.data} onClick={() => bind.mutate(true)}>主动恢复原码绑定</Button>}</View>}
    {recovery.error && <QueryState title='绑定恢复记录读取失败' error={new Error(recovery.error)} />}
    {notice && <View className='note wrap'>{notice}</View>}
    {(bind.error || lookup.error || copy.error) && <QueryState title='推荐操作未完成' error={bind.error ?? lookup.error ?? copy.error} />}
    <Button block fill='outline' loading={lookup.isPending} disabled={busy} onClick={() => lookup.mutate()}>查询当前关系与原码结果</Button>
    <Button block fill='outline' onClick={() => { void Taro.switchTab({ url: '/pages/home/index' }) }}>继续浏览商城</Button>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>帮助与支持</Button>
  </View>
}

export function ReferralPage() {
  const session = useSession()
  const raw = useRouter().params.invite
  const invite = invitationCode(raw)
  const query = useQuery({ queryKey: ['private', 'referral', session.epoch], enabled: !!session.user, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerReferralRead>('/distribution/me/referrer', { signal }) })
  // Register on the page component even before login. Never forward someone else's landing code.
  useShareAppMessage(() => {
    const own = session.epoch === sessionScope() && session.user && !query.isError ? query.data?.invitation_code : null
    return { title: '邀你逛拼捷商城', path: own && invitationCode(own) ? referralPath(own) : '/pages/home/index', imageUrl: '/assets/share-mall.png' }
  })
  return <>{raw !== undefined && <View className='page'><View className='note'>{invite ? `收到邀请码 ${invite}。登录后核对当前账户并主动确认，不会自动绑定。` : '分享邀请码无效，可继续浏览商城或手动填写正确邀请码。'}</View></View>}<AuthGate><Content key={session.epoch} invite={invite} /></AuthGate></>
}
