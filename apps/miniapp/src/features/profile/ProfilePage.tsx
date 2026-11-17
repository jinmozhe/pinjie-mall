import { useEffect, useRef, useState } from 'react'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { Button as NativeButton, Form, Image, Input, Text, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { ResponseModelConsumerUserRead } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { QueryState } from '@/components/QueryState'
import { privateAvatarUpload, privateRequest, sessionScope, updateSessionUser, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'
import { finishAuthentication } from '@/lib/auth-navigation'
import { assetUrl } from '@/platform/media'
import { ProfileFrame } from './ProfileFrame'
import camera from './assets/camera.svg'
import home from './assets/home.svg'
import person from './assets/person.svg'
import './profile.scss'

function Avatar({ url }: { url?: string | null }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => setFailed(false), [url])
  let source = ''
  let invalid = false
  if (url) { try { source = assetUrl(url) } catch { invalid = true } }
  return <>
    <View className='profile-avatar'>
      {source && !failed ? <Image src={source} mode='aspectFill' onError={() => setFailed(true)} /> : <View className='profile-avatar-placeholder'><View /><View /></View>}
    </View>
    {invalid && <View className='profile-feedback'>头像来源未获准入</View>}
    {failed && <NativeButton className='profile-text-action' onClick={() => setFailed(false)}>头像加载失败，点击重试</NativeButton>}
  </>
}

function Content() {
  const session = useSession()
  const onboarding = useRouter().params.onboarding === '1'
  const [name, setName] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [unknown, setUnknown] = useState<'avatar' | 'nickname' | null>(null)
  const [saved, setSaved] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const guard = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  function ensureCurrent() {
    if (!mounted.current || session.epoch !== sessionScope()) throw new Error('会话或页面已改变，请重新读取资料')
  }
  const query = useQuery({ queryKey: ['private', 'me', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerUserRead>('/users/me', { signal }) })
  useDidShow(() => { void query.refetch() })
  async function accepted(user: ResponseModelConsumerUserRead['data']) {
    await queryClient.cancelQueries({ queryKey: ['private', 'me', session.epoch] })
    ensureCurrent()
    updateSessionUser(user, session.epoch)
    queryClient.setQueryData(['private', 'me', session.epoch], user)
  }
  const save = useMutation({ mutationFn: async (submittedName: string) => {
    try {
      const displayName = submittedName.trim()
      if (!displayName || displayName.length > 100 || unknown) throw new Error('请填写 1 至 100 字昵称，并先查询未确认的修改结果')
      ensureCurrent()
      setNotice(''); setSaved(false)
      if (displayName !== query.data?.display_name) {
        setNotice('正在保存昵称…')
        setUnknown('nickname')
        const user = await privateRequest<ResponseModelConsumerUserRead>('/users/me', { method: 'PATCH', data: { display_name: displayName } })
        await accepted(user)
        setName(null); setUnknown(null)
      }
      ensureCurrent()
      setSaved(true); setNotice('昵称已保存。')
      if (onboarding) await finishAuthentication({ fromProfile: true })
    } finally { guard.current = false }
  } })
  const choose = useMutation({ mutationFn: async (path: string) => {
    try {
      setNotice('正在上传头像…'); setSaved(false)
      const file = await Taro.getFileInfo({ filePath: path })
      ensureCurrent()
      if (!('size' in file) || !Number.isFinite(file.size) || file.size <= 0 || file.size > 2 * 1024 * 1024) throw new Error('请选择不超过 2 MB 的 JPG、PNG 或 WebP 图片')
      const uploaded = await privateAvatarUpload(path)
      ensureCurrent()
      setNotice('正在更新头像…'); setUnknown('avatar')
      const user = await privateRequest<ResponseModelConsumerUserRead>('/users/me/avatar', { method: 'PUT', data: { asset_id: uploaded.id } })
      await accepted(user)
      setUnknown(null); setNotice('头像已更新。')
    } catch (failure) {
      setNotice('头像更新未完成，请查看错误提示。')
      throw failure
    } finally { guard.current = false }
  } })
  const remove = useMutation({ mutationFn: async () => {
    try {
      const answer = await Taro.showModal({ title: '移除头像', content: '确认后立即解除头像绑定，已上传的文件仍按商城资产规则保留。' })
      ensureCurrent()
      if (!answer.confirm) return
      setSaved(false); setNotice('正在移除头像…'); setUnknown('avatar')
      const user = await privateRequest<ResponseModelConsumerUserRead>('/users/me/avatar', { method: 'PUT', data: { asset_id: null } })
      await accepted(user)
      setUnknown(null); setNotice('头像已移除。')
    } catch (failure) {
      setNotice('头像移除未完成，请查看错误提示。')
      throw failure
    } finally { guard.current = false }
  } })
  async function confirmFacts() {
    if (guard.current) return
    guard.current = true
    try {
      const result = await query.refetch()
      if (!result.isError && result.data) {
        ensureCurrent()
        updateSessionUser(result.data, session.epoch)
        if (unknown === 'nickname') setName(null)
        setUnknown(null); setSaved(false)
        save.reset(); choose.reset(); remove.reset()
        setNotice(unknown === 'nickname'
          ? '已显示服务端当前昵称。未保存的内容请重新填写；在途请求仍可能完成，请核对后操作。'
          : '已读取当前头像，昵称输入已保留。上次请求仍可能完成，请核对后操作。')
      }
    } catch (failure) { setNotice(failure instanceof Error ? failure.message : '查询失败，请重试') }
    finally { guard.current = false }
  }
  const busy = save.isPending || choose.isPending || remove.isPending || leaving
  async function leave(target?: string) {
    if (guard.current || busy) return
    guard.current = true; setLeaving(true)
    try {
      ensureCurrent()
      if (target) await Taro.switchTab({ url: target })
      else await finishAuthentication({ fromProfile: true })
    } catch { setNotice('页面返回失败，请重试。已保存的资料无需重复提交。') }
    finally { guard.current = false; setLeaving(false) }
  }
  const error = save.error ?? choose.error ?? remove.error
  return <View className='profile-card'>
      {query.isPending ? <QueryState title='正在读取本人资料' /> : query.isError ? <QueryState title='本人资料读取失败' error={query.error} retry={() => { void confirmFacts() }} /> : <>
        <View className='profile-avatar-area'>
          <View className='profile-avatar-control'>
            <Avatar url={query.data.avatar} />
            <NativeButton className='profile-avatar-picker' ariaLabel='选择头像' openType='chooseAvatar' disabled={busy || !!unknown}
              loading={choose.isPending} onChooseAvatar={(event) => {
                if (!guard.current && !busy && !unknown && event.detail.avatarUrl) { guard.current = true; save.reset(); remove.reset(); choose.mutate(event.detail.avatarUrl) }
              }}><Image src={camera} mode='aspectFit' /></NativeButton>
          </View>
          {query.data.avatar && <NativeButton className='profile-text-action' disabled={busy || !!unknown} onClick={() => {
            if (!guard.current && !busy && !unknown) { guard.current = true; save.reset(); choose.reset(); remove.mutate() }
          }}>移除头像</NativeButton>}
        </View>
        <Form className='profile-edit-form' onSubmit={(event) => {
          const value: unknown = event.detail.value?.nickname
          if (!guard.current && !busy && !unknown && !choose.isError && typeof value === 'string') {
            if (saved && onboarding && value.trim() === query.data?.display_name) { void leave(); return }
            guard.current = true; remove.reset(); save.mutate(value)
          }
        }}>
          <View className='profile-label'>昵称</View>
          <Input className='profile-input' type='nickname' name='nickname' value={name ?? query.data.display_name ?? ''} maxlength={100}
            disabled={busy || !!unknown} placeholder='输入或使用微信昵称' placeholderClass='profile-placeholder'
            onInput={(event) => { setName(event.detail.value); setSaved(false) }} onBlur={(event) => {
              setName(event.detail.value)
              if (event.detail.value !== (query.data.display_name ?? '')) setSaved(false)
            }} />
          <NativeButton className='profile-save' formType='submit' loading={save.isPending} disabled={busy || !!unknown || choose.isError}>{onboarding ? '保存并继续' : '保存更新'}</NativeButton>
        </Form>
      </>}
      {(notice || unknown || error) && <View className='profile-feedback' role='alert'>
        {unknown && !busy ? `${unknown === 'avatar' ? '头像' : '昵称'}更新结果尚未确认，请先查询当前资料。` : notice}
        {error && <QueryState title={saved ? '资料已保存，页面返回未完成' : '资料操作未完成'} error={error} />}
        {unknown && <NativeButton className='profile-text-action' disabled={busy || query.isFetching} onClick={() => { void confirmFacts() }}>查询当前资料</NativeButton>}
        {choose.isError && !unknown && <NativeButton className='profile-text-action' disabled={busy} onClick={() => {
          choose.reset(); setNotice('头像未更新，您可重新选择或继续保存昵称。')
        }}>暂不修改头像</NativeButton>}
        {error && <NativeButton className='profile-text-action' disabled={busy} onClick={() => {
          void Taro.navigateTo({ url: '/subpackages/service/help/index' }).catch(() => setNotice('帮助页面打开失败，请重试。'))
        }}>获取帮助</NativeButton>}
      </View>}
      <View className='profile-navigation'>
        {onboarding ? <>
          <NativeButton className='profile-skip' disabled={busy} loading={leaving} onClick={() => { void leave() }}>暂时跳过</NativeButton>
        </> : <>
          <NativeButton className='profile-secondary' disabled={busy} onClick={() => { void leave('/pages/home/index') }}><Image src={home} mode='aspectFit' /><Text>返回首页</Text></NativeButton>
          <NativeButton className='profile-secondary' disabled={busy} onClick={() => { void leave('/pages/account/index') }}><Image src={person} mode='aspectFit' /><Text>进入我的</Text></NativeButton>
        </>}
      </View>
  </View>
}
export function ProfilePage() { const session = useSession(); return <ProfileFrame><AuthGate requirePhone={false}><Content key={session.epoch} /></AuthGate></ProfileFrame> }
