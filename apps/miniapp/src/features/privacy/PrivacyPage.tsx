import { View } from '@tarojs/components'

export function PrivacyPage() {
  return <View className='page'><View className='surface'><View className='title'>小程序隐私说明</View><View className='section-title'>登录与账户</View><View>登录时微信提供一次性登录凭证，服务端据此识别微信身份并创建独立商城账户。微信昵称和手机号不会自动用于合并其他账户。</View><View className='section-title'>购物与配送</View><View>您填写的姓名、联系电话和地址用于订单配送。购物车和订单归属于本人账户。请只提供完成服务所需的信息。</View><View className='section-title'>本机保存</View><View>登录凭据仅保存在运行内存。设备保存隐私确认、主动退出偏好，以及本人未完成结算的请求号、商品规格 ID、数量和地址 ID，用于避免重复下单。这里不保存登录密钥和完整收货地址。</View><View className='section-title'>退出与平台声明</View><View>您可从个人中心退出。真实微信登录开放前，运营方需在微信平台配置服务隐私保护指引和联系渠道；涉及资料的处理以平台公开的正式指引为准。</View></View></View>
}
