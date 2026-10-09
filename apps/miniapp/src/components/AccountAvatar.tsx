import { useEffect, useState } from 'react'
import { Image, View } from '@tarojs/components'
import { Button } from './Button'
import { assetUrl } from '@/platform/media'

export function AccountAvatar({ url }: { url: string | null | undefined }) {
  const [failed, setFailed] = useState(false)
  useEffect(() => { setFailed(false) }, [url])
  let source = ''
  let invalid = false
  if (url) { try { source = assetUrl(url) } catch { invalid = true } }
  return <View className='account-avatar-area'>
    <View className='account-avatar'>{source && !failed ? <Image src={source} mode='aspectFill' onError={() => setFailed(true)} /> : <View className='account-avatar-placeholder'>头像</View>}</View>
    {invalid && <View className='muted'>头像来源未获准入</View>}
    {failed && <><View className='muted'>头像加载失败</View><Button fill='outline' onClick={() => setFailed(false)}>重试图片</Button></>}
  </View>
}
