import { View } from '@tarojs/components'
import Taro from '@tarojs/taro'
import { Button } from '@/components/Button'
import { privacySections } from './privacy-sections'

export function PrivacyPage() {
  return <View className='page account-page'><View className='surface'><View className='title'>小程序隐私说明</View>{privacySections.map((section) => <View key={section.title}><View className='section-title'>{section.title}</View><View>{section.body}</View></View>)}</View><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/account/closure/index' }) }}>注销说明与前置核对</Button><Button block fill='outline' onClick={() => { void Taro.navigateTo({ url: '/subpackages/service/help/index' }) }}>帮助与联系运营</Button></View>
}
