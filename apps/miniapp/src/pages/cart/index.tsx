import Taro from '@tarojs/taro'
import { View } from '@tarojs/components'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'

export default function CartPage() {
  return <View className='page'><QueryState title='登录后查看购物车' detail='微信登录尚未接入，当前可先浏览商品和选择规格。' /><Button block type='primary' onClick={() => { void Taro.switchTab({ url: '/pages/home/index' }) }}>去逛逛</Button></View>
}
