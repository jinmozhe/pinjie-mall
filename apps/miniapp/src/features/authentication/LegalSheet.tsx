import { Button, ScrollView, View } from '@tarojs/components'
import { Popup } from '@nutui/nutui-react-taro/dist/es/packages/popup/popup'
import '@nutui/nutui-react-taro/dist/es/packages/popup/style'
import { privacySections } from '@/features/privacy'

export type LegalDocument = 'agreement' | 'privacy'

const agreementSections = [
  { title: '服务范围', body: '欢迎使用拼捷商城。我们提供商品浏览、购物车、订单查询、会员与推荐分享等服务。部分功能需要登录并完成手机号授权，实际可用服务以商城开放状态为准。' },
  { title: '账户使用', body: '微信身份用于识别您的商城账户。请通过本人微信使用服务，并按实际需要填写资料。未登录时，仍可浏览公开商品。请妥善保护账户，不向他人提供登录凭据。' },
  { title: '购物与售后', body: '下单前，请核对商品规格、数量、收货地址及应付金额。订单状态和可用的售后操作以商城展示的信息为准。支付、退款与提现结果以实际确认结果为准。' },
  { title: '会员与推荐', body: '会员权益及适用价格以商城展示和结算结果为准。推荐关系需要您主动确认，分享不保证获得奖励。佣金、积分和钱包余额具有不同用途，以对应规则及本人记录为准。' },
  { title: '信息与账户安全', body: '请提供真实、必要的信息，不在公开评价中填写个人敏感资料。您可在个人中心查看资料、账户安全、隐私说明与帮助。当前自助注销尚未开放，联系运营不代表注销已受理。' },
]
const numerals = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']

export function LegalSheet({ document, onClose }: { document: LegalDocument | null; onClose: () => void }) {
  const sections = document === 'agreement' ? agreementSections : privacySections
  const title = document === 'agreement' ? '用户协议' : '隐私条款'
  return <Popup className='auth-legal-sheet' visible={document !== null} position='bottom' round onClose={onClose} style={{ display: 'flex' }}
    overlayClassName='auth-legal-overlay'>
    <View className='auth-legal-header'>
      <View className='auth-legal-handle' />
      <View className='auth-legal-title'>{title}</View>
      <View className='auth-legal-subtitle'>请仔细阅读以下内容</View>
      <Button className='auth-legal-dismiss' ariaLabel={`关闭${title}`} onClick={onClose}><View className='auth-close-icon' /></Button>
    </View>
    <ScrollView key={document ?? 'closed'} scrollY className='auth-legal-scroll' showScrollbar enhanced>
      <View className='auth-legal-body'>
        {sections.map((section, index) => <View className='auth-legal-section' key={section.title}>
          <View className='auth-legal-heading'>{numerals[index]}、{section.title}</View>
          <View>{section.body}</View>
        </View>)}
      </View>
    </ScrollView>
    <View className='auth-legal-footer'>
      <View className='auth-legal-subtitle'>上下滑动查看全文</View>
      <Button className='auth-legal-close' onClick={onClose}>关闭</Button>
    </View>
  </Popup>
}
