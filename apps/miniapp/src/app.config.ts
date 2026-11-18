import tabBar from './tab-bar.json'

export default defineAppConfig({
  pages: ['pages/home/index', 'pages/category/index', 'pages/cart/index', 'pages/account/index'],
  subPackages: [
    { root: 'subpackages/catalog', pages: ['detail/index'] },
    { root: 'subpackages/account', pages: ['auth/index', 'addresses/index', 'privacy/index', 'profile/index', 'settings/index', 'sessions/index', 'closure/index'] },
    { root: 'subpackages/finance', pages: ['membership/index', 'wallets/index', 'ledgers/index', 'commissions/index', 'withdrawals/index', 'referral/index', 'points/index'] },
    { root: 'subpackages/trade', pages: ['checkout/index', 'orders/index', 'order-detail/index'] },
    { root: 'subpackages/service', pages: ['refund-apply/index', 'refunds/index', 'refund-detail/index', 'review/index', 'help/index'] },
  ],
  window: { navigationBarTitleText: '拼捷商城', navigationBarBackgroundColor: '#FFFFFF', navigationBarTextStyle: 'black', backgroundColor: '#F7F8FA' },
  tabBar: {
    color: tabBar.color, selectedColor: tabBar.selectedColor, backgroundColor: '#FFFFFF', borderStyle: 'white',
    list: tabBar.items.map(({ pagePath, text, asset }) => ({
      pagePath, text, iconPath: `assets/tab-${asset}.png`, selectedIconPath: `assets/tab-${asset}-active.png`,
    })),
  },
})
