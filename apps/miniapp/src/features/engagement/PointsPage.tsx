import { useState } from 'react'
import Taro, { useDidShow } from '@tarojs/taro'
import { Text, View } from '@tarojs/components'
import { useQuery } from '@tanstack/react-query'
import type { ConsumerPointsLedgerRead, ResponseModelConsumerPointsRead, ResponseModelPageResultConsumerPointsLedgerRead } from '@pinjie/api-client'
import { AuthGate } from '@/components/AuthGate'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'
import { privateRequest, useSession } from '@/lib/session'

const entryLabels: Record<ConsumerPointsLedgerRead['entry_type'], string> = { grant: '积分授予', spend: '积分支出', freeze: '积分冻结', release: '冻结释放', reverse: '积分冲销', expire: '积分到期' }
const sourceLabels: Record<ConsumerPointsLedgerRead['source_type'], string> = { invite: '邀请相关记录', order: '订单相关记录', refund: '退款相关记录', redemption: '兑换相关记录', manual: '人工调整记录' }
function Content() {
  const session = useSession()
  const [page, setPage] = useState(1)
  const account = useQuery({ queryKey: ['private', 'points', session.epoch], gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelConsumerPointsRead>('/users/me/points', { signal }) })
  const ledger = useQuery({ queryKey: ['private', 'points-ledgers', session.epoch, page], enabled: account.data?.state === 'opened' && !account.isError, gcTime: 0, queryFn: ({ signal }) => privateRequest<ResponseModelPageResultConsumerPointsLedgerRead>(`/users/me/points/ledgers?page=${page}&page_size=10`, { signal }) })
  useDidShow(() => { void account.refetch(); if (account.data?.state === 'opened') void ledger.refetch() })
  return <View className='page account-page'><View className='title'>我的积分</View>
    <View className='note'>积分独立于人民币钱包。当前提供余额和流水查询，兑换、抵扣与自动到期尚未开放；推荐绑定或分享不承诺积分奖励。</View>
    {account.isPending && <QueryState title='正在读取本人积分账户' />}
    {account.isError && <QueryState title='积分账户读取失败' error={account.error} retry={() => { void account.refetch() }} />}
    {account.data && !account.isError && <>{account.data.state === 'not_opened' ? <QueryState title='积分账户尚未建立' /> : account.data.account && <>
      <View className='surface'><View className='section-title'>积分余额</View><View className='finance-facts'><View>可用积分<Text>{account.data.account.available_points}</Text></View><View>冻结积分<Text>{account.data.account.frozen_points}</Text></View><View>追回欠款积分<Text>{account.data.account.debt_points}</Text></View></View><View className='muted'>账户版本 {account.data.account.revision}；更新于 {new Date(account.data.account.updated_at).toLocaleString()}</View><View className='muted'>欠款表示尚待追回的积分，不等同于可用积分，不自行合并为总余额。</View></View>
      <View className='section-title'>积分流水</View><View className='muted'>正数表示增加，负数表示减少。各余额变化分开展示，历史流水类型不代表对应功能当前开放。</View>
      {ledger.isPending && <QueryState title='正在读取积分流水' />}
      {ledger.isError && <QueryState title='积分流水读取失败' error={ledger.error} retry={() => { void ledger.refetch() }} />}
      {ledger.data && !ledger.isError && <>{!ledger.data.items.length && <QueryState title={page === 1 ? '暂无积分流水' : '本页暂无积分流水'} />}{ledger.data.items.map((entry) => <View className='surface' key={entry.id}><View className='section-title'>{entryLabels[entry.entry_type]}</View><View className='muted'>{sourceLabels[entry.source_type]} · {new Date(entry.created_at).toLocaleString()}</View><View className='finance-facts'><View>可用变化<Text>{entry.available_delta}</Text></View><View>冻结变化<Text>{entry.frozen_delta}</Text></View><View>欠款变化<Text>{entry.debt_delta}</Text></View></View><View className='muted wrap'>记录号：{entry.id}</View></View>)}{(ledger.data.total_pages > 1 || page > 1) && <View className='trade-row spread'><Button fill='outline' disabled={page <= 1 || ledger.isFetching} onClick={() => setPage(page - 1)}>上一页</Button><Text>{page} / {Math.max(1, ledger.data.total_pages)}</Text><Button fill='outline' disabled={page >= ledger.data.total_pages || ledger.isFetching} onClick={() => setPage(page + 1)}>下一页</Button></View>}</>}
    </>}</>}
    <Button block fill='outline' disabled={account.isFetching || ledger.isFetching} onClick={() => { void account.refetch(); if (account.data?.state === 'opened') void ledger.refetch() }}>刷新积分事实</Button>
    <Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>帮助与支持</Button>
  </View>
}
export function PointsPage() { const session = useSession(); return <AuthGate><Content key={session.epoch} /></AuthGate> }
