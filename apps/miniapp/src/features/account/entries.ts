import payment from './assets/payment.svg'
import parcel from './assets/package.svg'
import truck from './assets/truck.svg'
import refund from './assets/refund.svg'
import orders from './assets/orders.svg'
import member from './assets/member.svg'
import share from './assets/share.svg'
import points from './assets/points.svg'
import address from './assets/address.svg'
import wallet from './assets/wallet.svg'
import commission from './assets/commission.svg'
import history from './assets/history.svg'
import checkout from './assets/checkout.svg'
import profile from './assets/profile.svg'
import security from './assets/security.svg'
import privacy from './assets/privacy.svg'
import help from './assets/help.svg'

export const orderEntries = [
  { label: '待付款', icon: payment, path: '/subpackages/trade/orders/index?status=pending_payment' },
  { label: '待发货', icon: parcel, path: '/subpackages/trade/orders/index?status=awaiting_shipment' },
  { label: '待收货', icon: truck, path: '/subpackages/trade/orders/index?status=shipped' },
  { label: '售后服务', icon: refund, path: '/subpackages/service/refunds/index' },
  { label: '全部订单', icon: orders, path: '/subpackages/trade/orders/index' },
]

type ServiceEntry = { label: string; icon: string; tone: string; path: string; access: 'phone' | 'identity' | 'public' }
export const serviceEntries: ServiceEntry[] = [
  { label: '会员中心', icon: member, tone: 'gold', path: '/subpackages/finance/membership/index', access: 'phone' },
  { label: '推荐分享', icon: share, tone: 'coral', path: '/subpackages/finance/referral/index', access: 'phone' },
  { label: '我的积分', icon: points, tone: 'gold', path: '/subpackages/finance/points/index', access: 'phone' },
  { label: '收货地址', icon: address, tone: 'blue', path: '/subpackages/account/addresses/index', access: 'phone' },
  { label: '钱包与流水', icon: wallet, tone: 'orange', path: '/subpackages/finance/wallets/index', access: 'phone' },
  { label: '佣金记录', icon: commission, tone: 'teal', path: '/subpackages/finance/commissions/index', access: 'phone' },
  { label: '历史提现', icon: history, tone: 'indigo', path: '/subpackages/finance/withdrawals/index', access: 'phone' },
  { label: '继续结算', icon: checkout, tone: 'rose', path: '/subpackages/trade/checkout/index', access: 'phone' },
  { label: '个人资料', icon: profile, tone: 'cyan', path: '/subpackages/account/profile/index', access: 'identity' },
  { label: '账户安全', icon: security, tone: 'green', path: '/subpackages/account/settings/index', access: 'public' },
  { label: '隐私说明', icon: privacy, tone: 'slate', path: '/subpackages/account/privacy/index', access: 'public' },
  { label: '帮助支持', icon: help, tone: 'purple', path: '/subpackages/service/help/index', access: 'public' },
]
