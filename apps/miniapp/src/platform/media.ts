import Taro from '@tarojs/taro'

export function assetUrl(value: string): string {
  if (value.startsWith('/') && !value.startsWith('//') && !value.includes('\\')) return `${__ASSET_BASE_URL__}${value}`
  const match = /^(https?:\/\/[^/?#]+)(\/[^#]*)?$/.exec(value)
  if (match && match[1] === __ASSET_BASE_URL__) return value
  throw new Error('图片地址未通过资源源站校验')
}

export async function previewImages(urls: string[], current: string): Promise<void> {
  try { await Taro.previewImage({ urls: urls.map(assetUrl), current: assetUrl(current) }) }
  catch { await Taro.showToast({ title: '图片预览失败，请重试', icon: 'none' }) }
}
