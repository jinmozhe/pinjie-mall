declare const __API_BASE_URL__: string
declare const __ASSET_BASE_URL__: string
declare const __ROUTE_TRACE_ENABLED__: boolean
declare module '*.scss'
declare module '*.svg' { const source: string; export default source }
declare module '@nutui/icons-react-taro/dist/es/icons/configure' {
  export { configure } from '@nutui/icons-react-taro'
}
declare namespace JSX {
  interface IntrinsicElements {
    'mp-html': { content: string; selectable?: boolean; 'copy-link'?: boolean; 'use-anchor'?: boolean; 'container-style'?: string }
  }
}
