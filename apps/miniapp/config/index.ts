import { resolve } from 'node:path'
import { createRequire } from 'node:module'
import { defineConfig } from '@tarojs/cli'

export default defineConfig<'webpack5'>((_, { mode }) => {
  const requireFromApp = createRequire(resolve(__dirname, '../package.json'))
  const reactRoot = resolve(requireFromApp.resolve('react/package.json'), '..')
  const development = mode === 'development'
  const apiBase = process.env.TARO_APP_API_BASE_URL ?? (development ? 'http://127.0.0.1:18168' : '')
  const assetBase = process.env.TARO_APP_ASSET_BASE_URL ?? apiBase
  const basePattern = development ? /^https?:\/\/[^/?#@\s\\]+$/ : /^https:\/\/[^/?#@\s\\]+$/
  if (!basePattern.test(apiBase) || !basePattern.test(assetBase)) {
    throw new Error('必须显式设置合法 API/资源源站；生产仅允许 HTTPS，地址末尾不带斜线')
  }
  return {
    projectName: 'pinjie-miniapp',
    sourceRoot: 'src',
    outputRoot: 'dist',
    framework: 'react',
    compiler: { type: 'webpack5', prebundle: { enable: false } },
    designWidth(input) { const file = input && typeof input === 'object' ? input.file : ''; return file?.includes('node_modules') && file.includes('@nutui') ? 375 : 750 },
    deviceRatio: { 750: 1, 375: 2 },
    alias: { '@': resolve(__dirname, '../src'), 'react$': requireFromApp.resolve('react'), 'react': reactRoot },
    sass: { resource: [resolve(__dirname, '../node_modules/@nutui/nutui-react-taro/dist/styles/variables.scss')] },
    defineConstants: { __API_BASE_URL__: JSON.stringify(apiBase), __ASSET_BASE_URL__: JSON.stringify(assetBase) },
    cache: { enable: false },
    copy: { patterns: [{ from: resolve(__dirname, '../node_modules/mp-html/dist/mp-weixin'), to: 'dist/components/mp-html' }] },
    mini: {
      postcss: { pxtransform: { enable: true }, cssModules: { enable: false } },
      compile: { include: [resolve(__dirname, '../node_modules/@nutui')] },
    },
  }
})
