import { useState } from 'react'
import Taro, { useDidShow, useRouter } from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import { useMutation, useQuery } from '@tanstack/react-query'
import type { MiniappMemberRead, MiniappWalletRead, ResponseModelMiniappMemberRead, ResponseModelListMiniappWalletRead, ResponseModelPageResultMiniappWalletLedgerRead, ResponseModelPageResultMiniappCommissionRead, ResponseModelPageResultMiniappWithdrawalRead } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateRequest, sessionScope, useSession } from '@/lib/session'
import { queryClient } from '@/lib/query'

const date = (value: string | null) => value ? new Date(value).toLocaleString() : '尚无记录'
const memberLabels: Record<MiniappMemberRead['state'], string> = { not_opened: '尚未开通档案', no_level: '已开通，尚无会员等级', active: '会员等级有效', inactive: '所持会员等级已停用' }
const walletLabels: Record<MiniappWalletRead['wallet_type'], string> = { commission: '佣金钱包', consumption: '消费钱包' }
const entryLabels: Record<string, string> = { commission_settlement: '佣金结算', commission_recovery: '佣金追回', withdrawal_freeze: '提现冻结', withdrawal_release: '提现释放', withdrawal_paid: '提现资金确认' }
const commissionLabels: Record<string, string> = { frozen: '冻结中', settled: '已结算', recovered: '已追回' }
const withdrawalLabels: Record<string, string> = { requested: '待审核', approved: '审核通过', rejected: '审核拒绝', processing: '资金处理中', succeeded: '执行已确认', unknown: '执行结果未知' }

function Pager({ page, pages, busy, change }: { page: number; pages: number; busy: boolean; change: (page: number) => void }) {
  if (pages <= 1) return null
  return <View className='trade-row spread'><Button fill='outline' disabled={page <= 1 || busy} onClick={() => change(page - 1)}>上一页</Button><Text>{page} / {pages}</Text><Button fill='outline' disabled={page >= pages || busy} onClick={() => change(page + 1)}>下一页</Button></View>
}
function Support() { return <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>帮助与支持</Button> }
function Membership() {
  const session = useSession()
  const [unknown, setUnknown] = useState(false)
  const [accepted, setAccepted] = useState(false)
  const query = useQuery({ queryKey: ['private', 'membership', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelMiniappMemberRead>('/membership', { signal }) })
  useDidShow(() => { void query.refetch() })
  const activate = useMutation({ mutationFn: async () => {
    if (query.data?.state !== 'not_opened' || unknown) throw new Error('请先查询当前档案状态')
    const answer = await Taro.showModal({ title: '开通会员分销档案', content: '创建本人档案及双轨钱包。开通不保证获得会员等级或收益，不会绑定推荐人。' })
    if (!answer.confirm || session.epoch !== sessionScope()) return
    setUnknown(true)
    const result = await privateRequest<ResponseModelMiniappMemberRead>('/membership', { method: 'POST' })
    if (result.state === 'not_opened') throw new Error('服务端尚未确认档案开通')
    await queryClient.cancelQueries({ queryKey: ['private', 'membership', session.epoch] })
    if (session.epoch !== sessionScope()) throw new Error('会话已改变，请重新读取会员状态')
    setAccepted(true)
    setUnknown(false)
    queryClient.setQueryData(['private', 'membership', session.epoch], result)
    await queryClient.invalidateQueries({ queryKey: ['private', 'wallets'] })
  } })
  async function readFacts() {
    const result = await query.refetch()
    if (!result.isError && result.data && session.epoch === sessionScope()) {
      setUnknown(false)
      if (result.data.state !== 'not_opened') setAccepted(true)
    }
  }
  if (query.isPending) return <QueryState title='正在读取会员档案' />
  if (query.isError) return <QueryState title={accepted ? '档案已开通，最新信息读取失败' : '会员档案读取失败'} error={query.error} retry={() => { void readFacts() }} />
  const member = query.data
  return <View className='page account-page'><View className='title'>会员中心</View><View className='surface'><View className='section-title'>{memberLabels[member.state]}</View>{member.level_name && <View className='title wrap'>{member.level_name}</View>}{member.state === 'inactive' && <View className='note'>等级记录保留，停用等级不应用价格权益。</View>}{member.state === 'no_level' && <View className='note'>档案已开通，会员等级由服务端资格政策决定。</View>}{member.created_at && <View className='muted'>开通时间：{date(member.created_at)}</View>}{member.level_changed_at && <View className='muted'>等级变更：{date(member.level_changed_at)}</View>}</View><View className='surface'><View className='section-title'>推荐关系</View><View>{member.referral_bound ? '已有首次推荐关系' : '尚未绑定推荐关系'}</View>{member.bound_at && <View className='muted'>绑定时间：{date(member.bound_at)}</View>}<View className='muted'>邀请、分享与首次绑定入口留待后续开放，本页不会自动绑定。</View></View><View className='note'>会员价格由服务端统一报价确定，请在结算页确认实际价格。开通档案不等于取得等级，也不承诺佣金收益。</View>
    {unknown && <View className='note'>开通结果尚未确认，请查询当前档案，勿重复点击。</View>}{activate.error && <QueryState title={accepted ? '档案已开通，后续刷新未完成' : '开通结果未确认'} error={activate.error} />}
    {member.state === 'not_opened' ? <Button block loading={activate.isPending} disabled={activate.isPending || unknown} onClick={() => activate.mutate()}>主动开通档案</Button> : <Button block onClick={() => { void Taro.navigateTo({ url: '/subpackages/finance/wallets/index' }) }}>查看双轨钱包</Button>}
    <Button block fill='outline' disabled={activate.isPending} onClick={() => { void readFacts() }}>查询当前会员状态</Button><Support />
  </View>
}
function Wallets() {
  const session = useSession()
  const query = useQuery({ queryKey: ['private', 'wallets', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelListMiniappWalletRead>('/wallets', { signal }) })
  useDidShow(() => { void query.refetch() })
  return <View className='page account-page'><View className='title'>我的钱包</View>{query.isPending && <QueryState title='正在读取钱包余额' />}{query.isError && <QueryState title='钱包读取失败' error={query.error} retry={() => { void query.refetch() }} />}{query.data && !query.isError && query.data.map((wallet) => <View className='surface' key={wallet.wallet_type}><View className='section-title'>{walletLabels[wallet.wallet_type]}</View><View className='muted'>可用余额</View><View className='price finance-amount'>¥{wallet.available_amount}</View><View className='finance-balances'><View>冻结余额<View className='finance-amount'>¥{wallet.frozen_amount}</View></View><View>追回欠款<View className='finance-amount'>¥{wallet.debt_amount}</View></View></View><View className='note'>{wallet.wallet_type === 'commission' ? '仅接收已结算佣金，可按资格提现，不能用于购物。新提现申请尚未开放。' : '消费钱包用于后续购物抵扣，不能提现。当前抵扣尚未开放。'}新入账或提现释放可能优先清偿欠款。</View><View className='muted'>更新于 {date(wallet.updated_at)}</View><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: `/subpackages/finance/ledgers/index?type=${wallet.wallet_type}` }) }}>查看本钱包流水</Button></View>)}<View className='note'>两类钱包禁止互转，充值未开放。余额只展示服务端事实；冻结佣金记录与钱包提现冻结分别查询。</View><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/finance/membership/index' }) }}>查看或开通会员档案</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/finance/commissions/index' }) }}>佣金记录</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/finance/withdrawals/index' }) }}>历史提现记录</Button><Support /></View>
}
function Ledgers() {
  const session = useSession()
  const type = useRouter().params.type
  const valid = type === 'commission' || type === 'consumption'
  const [page, setPage] = useState(1)
  const query = useQuery({ queryKey: ['private', 'wallet-ledgers', session.epoch, type, page], enabled: valid, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelPageResultMiniappWalletLedgerRead>(`/wallets/${type}/ledgers?page=${page}&page_size=10`, { signal }) })
  useDidShow(() => { if (valid) void query.refetch() })
  if (!valid) return <QueryState title='钱包链接无效' />
  return <View className='page account-page'><View className='title'>{walletLabels[type]}流水</View><View className='note'>每条流水分别记录可用、冻结与欠款变化。负数表示减少，结余为该次变动后的历史快照。</View>{query.isPending && <QueryState title='正在读取钱包流水' />}{query.isError && <QueryState title='钱包流水读取失败' error={query.error} retry={() => { void query.refetch() }} />}{query.data && !query.isError && <>{!query.data.items.length && <QueryState title='暂无钱包流水' />}{query.data.items.map((entry) => <View className='surface' key={entry.id}><View className='section-title'>{entryLabels[entry.entry_type]}</View><View className='muted'>{date(entry.created_at)}</View><View className='finance-facts'><View>可用变化<Text>¥{entry.amount}</Text></View><View>冻结变化<Text>¥{entry.frozen_delta}</Text></View><View>欠款变化<Text>¥{entry.debt_delta}</Text></View></View><View className='field-label'>变动后结余</View><View className='muted wrap'>可用 ¥{entry.balance_after.available_amount} / 冻结 ¥{entry.balance_after.frozen_amount} / 欠款 ¥{entry.balance_after.debt_amount}</View><View className='muted'>账户版本 {entry.wallet_revision}</View></View>)}<Pager page={page} pages={query.data.total_pages} busy={query.isFetching} change={setPage} /></>}<Support /></View>
}
function Commissions() {
  const session = useSession()
  const [page, setPage] = useState(1)
  const query = useQuery({ queryKey: ['private', 'commissions', session.epoch, page], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelPageResultMiniappCommissionRead>(`/commissions?page=${page}&page_size=10`, { signal }) })
  useDidShow(() => { void query.refetch() })
  return <View className='page account-page'><View className='title'>佣金记录</View><View className='note'>记录来自实际成交与分佣事实。冻结佣金尚未进入钱包；达到结算时间仍需服务端完成结算，退款可能撤销或追回。</View>{query.isPending && <QueryState title='正在读取本人佣金' />}{query.isError && <QueryState title='佣金读取失败' error={query.error} retry={() => { void query.refetch() }} />}{query.data && !query.isError && <>{!query.data.items.length && <QueryState title='暂无佣金记录' />}{query.data.items.map((entry) => <View className='surface' key={entry.id}><View className='trade-row spread'><View className='section-title'>{commissionLabels[entry.status]}</View><View className='price-small finance-amount'>¥{entry.amount}</View></View><View>{entry.level} 级佣金</View><View className='finance-facts'><View>冻结时商品基数<Text>¥{entry.base_amount}</Text></View><View>已追回金额<Text>¥{entry.recovered_amount}</Text></View></View>{entry.rate !== null && <View className='muted wrap'>冻结时比例参数：{entry.rate}，实际佣金以记录金额为准。</View>}<View className='muted'>冻结：{date(entry.frozen_at)}</View><View className='muted'>最早结算：{date(entry.settle_after)}</View>{entry.status === 'frozen' && entry.settle_after && <View className='muted'>到期不表示已经结算，请以已结算事实为准。</View>}{entry.settled_at && <View className='muted'>结算：{date(entry.settled_at)}</View>}{entry.recovered_at && <View className='muted'>追回完成：{date(entry.recovered_at)}</View>}<View className='muted wrap'>记录号：{entry.id}</View></View>)}<Pager page={page} pages={query.data.total_pages} busy={query.isFetching} change={setPage} /></>}<Support /></View>
}
function Withdrawals() {
  const session = useSession()
  const [page, setPage] = useState(1)
  const query = useQuery({ queryKey: ['private', 'withdrawals', session.epoch, page], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelPageResultMiniappWithdrawalRead>(`/withdrawals?page=${page}&page_size=10`, { signal }) })
  useDidShow(() => { void query.refetch() })
  return <View className='page account-page'><View className='title'>历史提现记录</View><View className='note'>当前仅支持历史查询。新提现申请尚未开放；审核通过不代表打款完成，未知结果须继续查询或联系运营。</View>{query.isPending && <QueryState title='正在读取提现记录' />}{query.isError && <QueryState title='提现记录读取失败' error={query.error} retry={() => { void query.refetch() }} />}{query.data && !query.isError && <>{!query.data.items.length && <QueryState title='暂无历史提现记录' />}{query.data.items.map((entry) => <View className='surface' key={entry.id}><View className='trade-row spread'><View className='section-title'>{withdrawalLabels[entry.status]}</View><View className='price-small finance-amount'>¥{entry.amount}</View></View><View className='note'>{entry.funds_status === 'manual_confirmed' ? '运营已确认线下转账完成，此记录为人工确认事实。' : entry.funds_status === 'channel_confirmed' ? '服务端已取得渠道确认事实。' : '资金执行尚未确认，请勿据审核状态认定到账。'}</View><View className='muted'>申请：{date(entry.created_at)}</View>{entry.reviewed_at && <View className='muted'>审核：{date(entry.reviewed_at)}</View>}{entry.confirmed_at && <View className='muted'>资金确认：{date(entry.confirmed_at)}</View>}<View className='muted'>更新：{date(entry.updated_at)}</View><View className='muted wrap'>申请号：{entry.id}</View></View>)}<Pager page={page} pages={query.data.total_pages} busy={query.isFetching} change={setPage} /></>}<Button block fill='outline' disabled={query.isFetching} onClick={() => { void query.refetch() }}>刷新审核与资金事实</Button><Support /></View>
}
export function MembershipPage() { const session = useSession(); return <AuthGate><Membership key={session.epoch} /></AuthGate> }
export function WalletsPage() { const session = useSession(); return <AuthGate><Wallets key={session.epoch} /></AuthGate> }
export function WalletLedgersPage() { const session = useSession(); return <AuthGate><Ledgers key={session.epoch} /></AuthGate> }
export function CommissionsPage() { const session = useSession(); return <AuthGate><Commissions key={session.epoch} /></AuthGate> }
export function WithdrawalsPage() { const session = useSession(); return <AuthGate><Withdrawals key={session.epoch} /></AuthGate> }
