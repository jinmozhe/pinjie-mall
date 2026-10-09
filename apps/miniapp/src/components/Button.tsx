import type { ComponentProps } from 'react'
import { Button as NutButton } from '@nutui/nutui-react-taro/dist/es/packages/button/button'
import '@nutui/nutui-react-taro/dist/es/packages/button/style'

export function Button(props: ComponentProps<typeof NutButton>) {
  return <NutButton fill='solid' shape='square' {...props} />
}
