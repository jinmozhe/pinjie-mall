module.exports = {
  presets: [['taro', { framework: 'react', ts: true, compiler: 'webpack5' }]],
  plugins: [['import', { libraryName: '@nutui/icons-react-taro', libraryDirectory: 'dist/es/icons', camel2DashComponentName: false, style: false }, 'nutui-icons']],
}
