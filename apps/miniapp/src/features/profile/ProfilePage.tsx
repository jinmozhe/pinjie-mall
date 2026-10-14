import { useState } from 'react'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { Button as NativeButton, Form, Input, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { ConsumerAvatarAssetRead, ResponseModelConsumerUserRead } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { AccountAvatar } from '@/components/AccountAvatar'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateAvatarUpload, privateRequest, sessionScope, updateSessionUser, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'
import { finishAuthentication, profileGuideKey } from '@/lib/auth-navigation'

function Content() {
  const session = useSession()
  const onboarding = useRouter().params.onboarding === '1'
  const [name, setName] = useState<string | null>(null)
  const [asset, setAsset] = useState<ConsumerAvatarAssetRead | null>(null)
  const [notice, setNotice] = useState('')
  const [unknown, setUnknown] = useState(false)
  const query = useQuery({ queryKey: ['private', 'me', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerUserRead>('/users/me', { signal }) })
  useDidShow(() => { void query.refetch() })
  async function accepted(user: ResponseModelConsumerUserRead['data']) {
    await queryClient.cancelQueries({ queryKey: ['private', 'me', session.epoch] })
    updateSessionUser(user, session.epoch)
    queryClient.setQueryData(['private', 'me', session.epoch], user)
    setUnknown(false)
    setNotice('服务端已确认资料保存。')
  }
  const save = useMutation({ mutationFn: async (submittedName: string) => {
    const displayName = submittedName.trim()
    if (!displayName || displayName.length > 100 || unknown) throw new Error('请填写 1 至 100 字昵称，并先查询未确认的修改结果')
    setUnknown(true)
    const user = await privateRequest<ResponseModelConsumerUserRead>('/users/me', { method: 'PATCH', data: { display_name: displayName } })
    await accepted(user)
    setName(null)
  } })
  const choose = useMutation({ mutationFn: async (path: string) => {
    setNotice('')
    const file = await Taro.getFileInfo({ filePath: path })
    if (session.epoch !== sessionScope()) return
    if (!('size' in file) || !Number.isFinite(file.size) || file.size <= 0 || file.size > 2 * 1024 * 1024) throw new Error('请选择不超过 2 MB 的 JPG、PNG 或 WebP 图片')
    const uploaded = await privateAvatarUpload(path)
    setAsset(uploaded)
    setNotice('头像已上传，请点击“保存所选头像”完成绑定。')
  } })
  const bind = useMutation({ mutationFn: async (remove: boolean) => {
    if (unknown || !remove && !asset) throw new Error('请先查询上次修改结果，或选择头像')
    if (remove) {
      const answer = await Taro.showModal({ title: '移除头像', content: '解除当前头像绑定，已上传的文件仍按商城资产规则保留。' })
      if (!answer.confirm || session.epoch !== sessionScope()) return
    }
    setUnknown(true)
    const user = await privateRequest<ResponseModelConsumerUserRead>('/users/me/avatar', { method: 'PUT', data: { asset_id: remove ? null : asset!.id } })
    await accepted(user)
    setAsset(null)
  } })
  async function confirmFacts() {
    const result = await query.refetch()
    if (!result.isError && result.data && session.epoch === sessionScope()) {
      updateSessionUser(result.data, session.epoch)
      setUnknown(false)
      setNotice('已读取当前资料。请核对昵称和头像；在途请求仍可能完成，后续修改需主动确认。')
    }
  }
  const busy = save.isPending || choose.isPending || bind.isPending
  async function continueOnboarding() {
    if (!session.user) return
    try {
      Taro.setStorageSync(profileGuideKey(session.user.id), true)
      await finishAuthentication()
    } catch { setNotice('返回或保存引导偏好失败，请重试') }
  }
  if (query.isPending || query.isError) return <View className='page account-page'>
    {query.isPending ? <QueryState title='正在读取本人资料' /> : <QueryState title='本人资料读取失败' error={query.error} retry={() => { void query.refetch() }} />}
    {notice && <View className='note'>{notice}</View>}
    {onboarding && <Button block fill='outline' onClick={() => { void continueOnboarding() }}>暂时跳过</Button>}
  </View>
  return <View className='page account-page'><View className='title'>个人资料</View>
    <View className='surface'><View className='section-title'>头像</View><AccountAvatar url={asset?.url ?? query.data.avatar} />{asset && <View className='muted'>所选图片尚未绑定为头像</View>}
      <NativeButton className='native-account-button' openType='chooseAvatar' loading={choose.isPending} disabled={busy || unknown}
        onChooseAvatar={(event) => { if (event.detail.avatarUrl) choose.mutate(event.detail.avatarUrl) }}>选择头像</NativeButton>
      <View className='category-strip'>{asset && <Button loading={bind.isPending} disabled={busy || unknown} onClick={() => bind.mutate(false)}>保存所选头像</Button>}{query.data.avatar && <Button fill='outline' disabled={busy || unknown} onClick={() => bind.mutate(true)}>移除头像</Button>}</View><View className='muted'>由您主动选择头像。图片最多 2 MB，格式由服务端校验。</View></View>
    <Form className='surface profile-form' onSubmit={(event) => {
      const value: unknown = event.detail.value?.nickname
      if (!busy && !unknown && typeof value === 'string') save.mutate(value)
    }}><View className='field-label'>当前昵称</View><View className='wrap'>{query.data.display_name || '尚未设置'}</View><View className='field-label'>修改昵称</View>
      <Input type='nickname' name='nickname' value={name ?? query.data.display_name ?? ''} maxlength={100} disabled={busy || unknown} placeholder='请输入昵称' onInput={(event) => setName(event.detail.value)} onBlur={(event) => setName(event.detail.value)} />
      <NativeButton className='native-account-button' formType='submit' loading={save.isPending} disabled={busy || unknown}>保存昵称</NativeButton>
    </Form>
    {notice && <View className='note'>{notice}</View>}{unknown && <View className='note'>本次修改结果尚未确认，请先查询当前资料。请勿直接重复提交。</View>}{(save.error || choose.error || bind.error) && <QueryState title='资料操作未完成' error={save.error ?? choose.error ?? bind.error} />}
    <Button block fill='outline' disabled={busy} onClick={() => { void confirmFacts() }}>查询当前资料</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>获取帮助</Button>
    {onboarding && <><Button block disabled={busy} onClick={() => { void continueOnboarding() }}>完成并继续</Button><Button block fill='outline' disabled={busy} onClick={() => { void continueOnboarding() }}>暂时跳过</Button></>}
  </View>
}
export function ProfilePage() { const session = useSession(); return <AuthGate requirePhone={false}><Content key={session.epoch} /></AuthGate> }
