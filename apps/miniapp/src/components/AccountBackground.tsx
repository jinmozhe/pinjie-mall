import { Image } from '@tarojs/components'
import background from '@/assets/account-background.svg'

export function AccountBackground() {
  return <Image className='account-screen-background' src={background} mode='aspectFill' />
}
