import '@tarojs/taro'

declare module '@tarojs/taro' {
  interface TaroStatic {
    /** 微信订单发货管理的确认收货组件，结果仍需服务端查询。 */
    openBusinessView(option: {
      businessType: 'weappOrderConfirm'
      extraData: { transaction_id: string }
    }): Promise<{ errMsg: string }>
  }
}
