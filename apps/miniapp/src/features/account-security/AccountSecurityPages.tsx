import { useCallback, useEffect, useRef, useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import type { ConsumerClosureCheckRead, ConsumerSessionTargets } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { logout, sessionScope, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'
import { readClosurePrecheck, readRevocation, readSessions, revokeSessions } from './api'
import { revocationConfirmed, validSessionIds } from './domain'
import { clearRevocation, loadRevocation, saveRevocation } from './intent'
import type { RevocationIntent } from './intent'

const date = (value: string) => new Date(value).toLocaleString()
const message = (error: unknown) => error instanceof Error ? error.message : '操作未完成，请稍后查询或联系支持'
const navigate = (url: string) => Taro.navigateTo({ url })
const stateLabels = { active: '有效会话', expired: '已过期', revoked: '已撤销' }

function useNavigation() {
  const [navigationError, setNavigationError] = useState('')
  async function open(url: string) {
    setNavigationError('')
    try { await navigate(url) }
    catch { setNavigationError('页面打开失败，请稍后重试') }
  }
  return { open, navigationError }
}

export function SettingsPage() {
  const session = useSession()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const guard = useRef(false)
  async function signOut() {
    if (guard.current) return
    guard.current = true; setBusy(true); setError('')
    const epoch = sessionScope()
    try {
      const answer = await Taro.showModal({ title: '退出登录', content: '清除本机内存会话和私有查询缓存，停止自动登录。未完成交易的恢复记录保留，之后仅原账户可继续查询。', confirmText: '退出登录', cancelText: '取消' })
      if (answer.confirm && epoch === sessionScope()) await logout()
    } catch (failure) { setError(message(failure)) }
    finally { guard.current = false; setBusy(false) }
  }
  async function open(url: string) { try { await navigate(url) } catch { setError('页面打开失败，请稍后重试') } }
  return <View className='page account-page security-page'>
    <View className='title'>账户设置</View>
    <View className='surface'><View className='section-title'>账户与安全</View><View className='muted'>{session.user ? '已登录，账户资料和会话仅向本人展示。' : '尚未登录，可继续阅读隐私与注销说明。'}</View>
      <Button block fill='outline' disabled={busy} onClick={() => { void open('/subpackages/account/profile/index') }}>个人资料</Button>
      <Button block fill='outline' disabled={busy} onClick={() => { void open('/subpackages/account/sessions/index') }}>登录会话管理</Button>
      <Button block fill='outline' disabled={busy} onClick={() => { void open('/subpackages/account/closure/index') }}>注销说明与前置核对</Button>
    </View>
    <View className='surface'><View className='section-title'>隐私与服务</View><Button block fill='outline' onClick={() => { void open('/subpackages/account/privacy/index') }}>隐私说明</Button><Button block fill='outline' onClick={() => { void open('/subpackages/service/help/index') }}>帮助与联系运营</Button></View>
    {(error || session.error) && <View className='note'>{error || session.error}</View>}
    {session.user && <Button block fill='outline' loading={busy} disabled={busy} onClick={() => { void signOut() }}>退出登录</Button>}
  </View>
}

function Sessions() {
  const session = useSession()
  const { open, navigationError } = useNavigation()
  const [page, setPage] = useState(1)
  const [intent, setIntent] = useState<RevocationIntent | null>(null)
  const [storageError, setStorageError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [canRecover, setCanRecover] = useState(false)
  const [initialized, setInitialized] = useState(false)
  const guard = useRef(false)
  const owner = session.user?.id
  const query = useQuery({ queryKey: ['private', 'sessions', session.epoch, page], gcTime: 0, queryFn: ({ signal }) => readSessions(page, signal) })
  const initialize = useCallback(() => {
    if (owner) {
      try { setIntent(loadRevocation(owner)); setStorageError('') }
      catch (failure) { setStorageError(message(failure)) }
      setInitialized(true)
    }
    setCanRecover(false)
  }, [owner])
  useEffect(initialize, [initialize])
  useDidShow(() => {
    initialize()
    void query.refetch()
  })
  function current(epoch: number) { return epoch === sessionScope() }
  async function accept(target: ConsumerSessionTargets, result: Awaited<ReturnType<typeof readRevocation>>, epoch: number) {
    if (!current(epoch) || !owner) return
    if (!revocationConfirmed(target, result)) {
      setCanRecover(result.sessions.every((item) => item.state !== 'not_found'))
      setNotice(result.sessions.some((item) => item.state === 'not_found') ? '原目标有记录无法查询，不能确认撤销，请联系运营核对。' : '原目标仍有有效会话，可主动恢复原集合。新登录的会话不在本次目标中。')
      return
    }
    setCanRecover(false)
    setNotice('原目标均已失效，当前会话保留。')
    try { clearRevocation(owner); setIntent(null); setStorageError('') }
    catch (failure) { setStorageError(`失效事实已确认，本机恢复记录清理失败：${message(failure)}`) }
    try { await queryClient.invalidateQueries({ queryKey: ['private', 'sessions', epoch] }, { throwOnError: true }) }
    catch (failure) { if (current(epoch)) setNotice(`原目标均已失效，会话列表刷新失败：${message(failure)}。请刷新列表。`) }
  }
  async function begin(ids: string[]) {
    if (!owner || guard.current || intent || storageError || !initialized || !validSessionIds(ids)) return
    guard.current = true; setBusy(true); setNotice(''); setCanRecover(false)
    const epoch = session.epoch
    let sent = false
    try {
      const target: ConsumerSessionTargets = { session_ids: [...ids] }
      const answer = await Taro.showModal({ title: '撤销登录会话', content: `撤销已选定的 ${ids.length} 个其他小程序会话，其登录凭据将失效。当前会话保留；重新登录会创建新会话。`, confirmText: '撤销会话', cancelText: '取消' })
      if (!answer.confirm || !current(epoch)) return
      const next: RevocationIntent = { version: 1, userId: owner, target }
      saveRevocation(next)
      setIntent(next)
      sent = true
      const result = await revokeSessions(target)
      await accept(target, result, epoch)
    } catch (failure) { if (current(epoch)) setNotice(sent ? `撤销结果未确认：${message(failure)}。请先查询原目标。` : `尚未发送撤销请求：${message(failure)}。请重试或联系支持。`) }
    finally { guard.current = false; if (current(epoch)) setBusy(false) }
  }
  async function resolve(recover = false) {
    if (!intent || guard.current || (recover && !canRecover)) return
    guard.current = true; setBusy(true); setCanRecover(false); setNotice('')
    const epoch = session.epoch
    try {
      if (recover) {
        const answer = await Taro.showModal({ title: '恢复原撤销操作', content: '仅撤销之前确认的原会话集合，不包含之后新登录的会话。', confirmText: '确认恢复', cancelText: '取消' })
        if (!answer.confirm || !current(epoch)) return
      }
      const result = await (recover ? revokeSessions(intent.target) : readRevocation(intent.target))
      await accept(intent.target, result, epoch)
    } catch (failure) { if (current(epoch)) setNotice(`原目标结果未确认：${message(failure)}。保留记录并联系支持，勿改用新集合。`) }
    finally { guard.current = false; if (current(epoch)) setBusy(false) }
  }
  const blocked = busy || !!intent || !!storageError || !initialized || query.isFetching || query.isError
  const data = query.data
  return <View className='page account-page security-page'><View className='title'>登录会话管理</View>
    <View className='note'>这里展示本人微信小程序登录会话。同一设备重新登录也可能产生新会话，名称和网络地址不能证明物理设备身份。撤销后正在执行的请求不保证回滚，交易结果仍需查询。</View>
    {storageError && <View className='note'>{storageError}</View>}{notice && <View className='note'>{notice}</View>}{navigationError && <View className='note'>{navigationError}</View>}
    {intent && <View className='surface'><View className='section-title'>原撤销操作待核对</View><View>保留了 {intent.target.session_ids.length} 个原目标，不会自动重复执行。</View><Button block disabled={busy} loading={busy} onClick={() => { void resolve() }}>查询原目标结果</Button>{canRecover && <Button block fill='outline' disabled={busy || !!storageError} onClick={() => { void resolve(true) }}>主动恢复原集合</Button>}</View>}
    {query.isPending && <QueryState title='正在读取登录会话' />}{query.isError && <QueryState title='会话读取失败' error={query.error} retry={() => { void query.refetch() }} />}
    {data && !query.isError && <>
      <View className='surface'><View>其他有效会话：{data.other_active_total}</View><View className='muted'>一次最多处理 100 个，确认后仅撤销当时列出的目标。查询信息变化后请重新核对。</View><Button block fill='outline' disabled={blocked || !data.other_active_ids.length} onClick={() => { void begin(data.other_active_ids) }}>撤销其他有效会话{data.other_active_total > 100 ? '（本批最多100个）' : ''}</Button></View>
      {!data.items.length && <QueryState title='暂无保留的会话记录' />}
      {data.items.map((item) => <View className='surface' key={item.id}><View className='trade-row spread'><View className='section-title'>{item.device_name || '微信小程序会话'}</View><Text className='label'>{item.is_current ? '当前会话' : stateLabels[item.state]}</Text></View><View className='muted'>登录：{date(item.created_at)}</View><View className='muted'>最近会话活动：{date(item.last_seen_at)}</View><View className='muted'>闲置截止：{date(item.idle_expires_at)}</View><View className='muted'>最长有效期：{date(item.absolute_expires_at)}</View>{item.ip_masked && <View className='muted wrap'>登录网络段：{item.ip_masked}</View>}{item.revoked_at && <View className='muted'>撤销：{date(item.revoked_at)}</View>}{!item.is_current && item.state === 'active' && <Button block fill='outline' disabled={blocked} onClick={() => { void begin([item.id]) }}>撤销此会话</Button>}</View>)}
      <View className='category-strip'><Button fill='outline' disabled={busy || page <= 1 || query.isFetching} onClick={() => setPage(page - 1)}>上一页</Button><Text>第 {page} 页 · 共 {data.total} 条</Text><Button fill='outline' disabled={busy || page >= data.total_pages || query.isFetching} onClick={() => setPage(page + 1)}>下一页</Button></View>
    </>}
    <Button block fill='outline' disabled={busy || query.isFetching} onClick={() => { void query.refetch() }}>刷新会话列表</Button><Button block fill='outline' onClick={() => { void open('/subpackages/service/help/index') }}>帮助与支持</Button>
  </View>
}

const checkLabels: Record<ConsumerClosureCheckRead['key'], [string, string]> = {
  orders: ['订单与履约', '/subpackages/trade/orders/index'], payments: ['待确认付款', '/subpackages/trade/orders/index'],
  refunds: ['售后申请', '/subpackages/service/refunds/index'], refund_execution: ['退款执行或异常收款退款', '/subpackages/service/help/index'],
  withdrawals: ['提现审核与资金确认', '/subpackages/finance/withdrawals/index'], commissions: ['待结算佣金', '/subpackages/finance/commissions/index'],
  wallets: ['钱包余额、冻结或欠款', '/subpackages/finance/wallets/index'], points: ['积分余额、冻结或欠款', '/subpackages/finance/points/index'],
}
function ClosureFacts() {
  const session = useSession()
  const { open, navigationError } = useNavigation()
  const query = useQuery({ queryKey: ['private', 'closure-precheck', session.epoch], gcTime: 0, staleTime: 0, queryFn: ({ signal }) => readClosurePrecheck(signal) })
  useDidShow(() => { void query.refetch() })
  return <View className='surface'><View className='section-title'>本人当前需核对事项</View>{query.isPending && <QueryState title='正在核对交易与账户状态' />}{query.isError && <QueryState title='前置核对失败，当前情况尚未确认' error={query.error} retry={() => { void query.refetch() }} />}{query.data && !query.isError && <>
    <View className='muted'>核对时间：{date(query.data.checked_at)}</View><View className='muted'>钱包：{query.data.wallet_state === 'not_opened' ? '未开通' : '已开通'} · 积分账户：{query.data.points_state === 'not_opened' ? '未建立' : '已建立'}</View>
    {query.data.checks.map((check) => <View className='order-line' key={check.key}><View className='trade-row spread'><Text>{checkLabels[check.key][0]}</Text><Text>{check.needs_review ? '需进一步核对' : '本次未发现相关待处理事项'}</Text></View>{check.needs_review && <Button block fill='outline' onClick={() => { void open(checkLabels[check.key][1]) }}>查看与处理</Button>}</View>)}
    <View className='note'>这些信息仅用于咨询与核对。交易可能继续变化，全部未发现待处理事项也不表示已符合注销条件，不会自动放弃余额、积分或售后权利。</View>
  </>}{navigationError && <View className='note'>{navigationError}</View>}<Button block fill='outline' disabled={query.isFetching} onClick={() => { void query.refetch() }}>重新核对当前状态</Button></View>
}
export function ClosurePage() {
  const session = useSession()
  const { open, navigationError } = useNavigation()
  return <View className='page account-page security-page'><View className='title'>注销说明与前置核对</View><View className='note'>自助注销尚未开放。本页只读取当前状态，不提交注销申请、不删除账号、不解除微信身份绑定。</View><View className='surface'><View className='section-title'>先处理交易与权益</View><View>注销前需核对订单、履约、付款与退款、提现、佣金、钱包余额及积分。服务端尚未确定完整注销与权益处置规则，当前保留查询和联系运营入口。</View><View className='section-title'>历史资料保留边界</View><View>订单、付款、退款、分佣、钱包流水及相关审计需按业务与合规保留策略处理。退出登录不会删除账户；注销也不能承诺立即物理删除全部历史资料。联系运营不代表注销已受理或完成。</View></View><AuthGate><ClosureFacts key={session.epoch} /></AuthGate>{navigationError && <View className='note'>{navigationError}</View>}<Button block fill='outline' onClick={() => { void open('/subpackages/service/help/index') }}>联系运营咨询</Button><Button block fill='outline' onClick={() => { void open('/subpackages/account/privacy/index') }}>查看隐私说明</Button></View>
}
export function SessionsPage() { const session = useSession(); return <AuthGate><Sessions key={session.epoch} /></AuthGate> }
