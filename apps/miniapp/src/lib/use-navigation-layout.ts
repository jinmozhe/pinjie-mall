import { useState } from 'react'
import Taro, { useDidShow, useResize } from '@tarojs/taro'

type Layout = { top: number; height: number; side: number }

function readLayout(): { layout: Layout | null; error: string } {
  try {
    const { statusBarHeight, windowWidth, windowHeight } = Taro.getWindowInfo()
    const menu = Taro.getMenuButtonBoundingClientRect()
    const values = [statusBarHeight, windowWidth, windowHeight, menu.top, menu.height, menu.left, menu.right]
    if (typeof statusBarHeight !== 'number' || !values.every(Number.isFinite) || statusBarHeight < 0 || windowWidth <= 0 || windowHeight <= 0
      || menu.height <= 0 || menu.top < statusBarHeight || menu.left <= 0 || menu.right > windowWidth || menu.right <= menu.left) {
      throw new Error('Invalid navigation bounds')
    }
    const height = Math.max(44, menu.height + 2 * (menu.top - statusBarHeight))
    const side = Math.max(44, windowWidth - menu.left + 8)
    if (side * 2 >= windowWidth || statusBarHeight + height >= windowHeight) throw new Error('Insufficient viewport')
    return { layout: { top: statusBarHeight, height, side }, error: '' }
  } catch { return { layout: null, error: '页面布局加载失败，请重试。' } }
}

export function useNavigationLayout() {
  const [state, setState] = useState(readLayout)
  const refresh = () => setState(readLayout())
  useDidShow(refresh)
  useResize(refresh)
  return { ...state, refresh }
}
