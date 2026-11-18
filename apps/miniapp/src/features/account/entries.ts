import type { IconName } from '@/components/Icon'

type Entry = { label: string; icon: IconName; path: string }
export const orderEntries: Entry[] = [
  { label: '待付款', icon: 'ToPay', path: '/subpackages/trade/orders/index?status=pending_payment' },
  { label: '待发货', icon: 'ToReceive', path: '/subpackages/trade/orders/index?status=awaiting_shipment' },
  { label: '待收货', icon: 'Transit', path: '/subpackages/trade/orders/index?status=shipped' },
  { label: '售后服务', icon: 'Refund', path: '/subpackages/service/refunds/index' },
  { label: '全部订单', icon: 'Order', path: '/subpackages/trade/orders/index' },
]

type ServiceEntry = Entry & { tone: string; access: 'phone' | 'identity' | 'public' }
export const serviceEntries: ServiceEntry[] = [
  { label: '会员中心', icon: 'User', tone: 'member', path: '/subpackages/finance/membership/index', access: 'phone' },
  { label: '推荐分享', icon: 'Share', tone: 'coral', path: '/subpackages/finance/referral/index', access: 'phone' },
  { label: '我的积分', icon: 'Star', tone: 'gold', path: '/subpackages/finance/points/index', access: 'phone' },
  { label: '收货地址', icon: 'Location', tone: 'blue', path: '/subpackages/account/addresses/index', access: 'phone' },
  { label: '钱包与流水', icon: 'Wallet', tone: 'orange', path: '/subpackages/finance/wallets/index', access: 'phone' },
  { label: '佣金记录', icon: 'Prices', tone: 'teal', path: '/subpackages/finance/commissions/index', access: 'phone' },
  { label: '历史提现', icon: 'Clock', tone: 'indigo', path: '/subpackages/finance/withdrawals/index', access: 'phone' },
  { label: '继续结算', icon: 'ToPay', tone: 'rose', path: '/subpackages/trade/checkout/index', access: 'phone' },
  { label: '个人资料', icon: 'Edit', tone: 'cyan', path: '/subpackages/account/profile/index', access: 'identity' },
  { label: '账户安全', icon: 'ShieldCheck', tone: 'green', path: '/subpackages/account/settings/index', access: 'public' },
  { label: '隐私说明', icon: 'ShieldCheck', tone: 'slate', path: '/subpackages/account/privacy/index', access: 'public' },
  { label: '帮助支持', icon: 'Service', tone: 'purple', path: '/subpackages/service/help/index', access: 'public' },
]
