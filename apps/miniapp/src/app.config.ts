export default defineAppConfig({
  pages: ['pages/home/index', 'pages/category/index', 'pages/cart/index', 'pages/account/index'],
  subPackages: [
    { root: 'subpackages/catalog', pages: ['detail/index'] },
    { root: 'subpackages/account', pages: ['addresses/index', 'privacy/index'] },
    { root: 'subpackages/trade', pages: ['checkout/index', 'orders/index', 'order-detail/index'] },
    { root: 'subpackages/service', pages: ['refund-apply/index', 'refunds/index', 'refund-detail/index', 'review/index', 'help/index'] },
  ],
  window: { navigationBarTitleText: '拼捷商城', navigationBarBackgroundColor: '#FFFFFF', navigationBarTextStyle: 'black', backgroundColor: '#F7F8FA' },
  tabBar: {
    color: '#475467', selectedColor: '#B42318', backgroundColor: '#FFFFFF', borderStyle: 'white',
    list: [
      { pagePath: 'pages/home/index', text: '首页', iconPath: 'assets/tab-home.png', selectedIconPath: 'assets/tab-home-active.png' },
      { pagePath: 'pages/category/index', text: '分类', iconPath: 'assets/tab-category.png', selectedIconPath: 'assets/tab-category-active.png' },
      { pagePath: 'pages/cart/index', text: '购物车', iconPath: 'assets/tab-cart.png', selectedIconPath: 'assets/tab-cart-active.png' },
      { pagePath: 'pages/account/index', text: '我的', iconPath: 'assets/tab-account.png', selectedIconPath: 'assets/tab-account-active.png' },
    ],
  },
})
