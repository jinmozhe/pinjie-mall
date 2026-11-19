import { View } from '@tarojs/components'
import {
  ArrowLeft, ArrowRight, Cart, Category, Check, Clock, Close, Edit, Home,
  Location, Minus, Order, Photograph, Plus, Prices, Refund, Search, Service,
  Share, ShieldCheck, Star, ToPay, ToReceive, Transit, User, Wallet, Weixin,
} from '@nutui/icons-react-taro'

// Keep explicit imports so Babel loads only this application's icon subset.
const icons = {
  ArrowLeft, ArrowRight, Cart, Category, Check, Clock, Close, Edit, Home,
  Location, Minus, Order, Photograph, Plus, Prices, Refund, Search, Service,
  Share, ShieldCheck, Star, ToPay, ToReceive, Transit, User, Wallet, Weixin,
}
export type IconName = keyof typeof icons

/** Decorative glyph. Put the accessible label on the containing control. */
export function Icon({ name, className = '', size }: { name: IconName; className?: string; size?: number }) {
  const Glyph = icons[name]
  return <View className={`app-icon ${className}`} ariaHidden style={size === undefined ? undefined : { width: `${size}rpx`, height: `${size}rpx` }}>
    <Glyph size='100%' />
  </View>
}
