import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { Image, View, Button } from '@tarojs/components'
import { assetUrl } from '@/platform/media'

export function ProductImage({ url, mode = 'aspectFill', style, onClick }: { url?: string; mode?: 'aspectFill' | 'aspectFit' | 'widthFix'; style?: CSSProperties; onClick?: () => void }) {
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => { setFailed(false); setAttempt(0) }, [url])
  let source = ''
  let rejected = false
  if (url) {
    try { source = assetUrl(url) } catch { rejected = true }
  }
  return <View className='image-box' style={style}>
    {!url || rejected || failed ? <View className='image-failure'>
      {!url ? '暂无商品图片' : rejected ? '图片来源未获准入' : '图片加载失败'}
      {failed && !rejected && <Button onClick={(event) => { event.stopPropagation(); setFailed(false); setAttempt(attempt + 1) }}>重试图片</Button>}
    </View> : <Image key={attempt} src={source} mode={mode} lazyLoad onError={() => setFailed(true)} onClick={onClick} style={{ width: '100%', height: mode === 'widthFix' ? 'auto' : '100%' }} />}
  </View>
}
