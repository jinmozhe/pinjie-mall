import Taro from '@tarojs/taro'
import { View } from '@tarojs/components'
import { Button } from '@/components/Button'
import { QueryState } from '@/components/QueryState'

export default function AccountPage() {
  return <View className='page'><QueryState title='欢迎来到拼捷商城' detail='当前未登录。订单、收货地址及钱包将在微信登录和相关业务接入后开放。' /><Button block type='primary' onClick={() => { void Taro.switchTab({ url: '/pages/category/index' }) }}>浏览商品分类</Button></View>
}
