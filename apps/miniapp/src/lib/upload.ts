import Taro from '@tarojs/taro'
import type { MiniappAvatarAssetRead } from '@pinjie/api-client'
import { ApiError } from './api'
import type { RequestSignal } from './cancellation'

export function parseAvatarUpload(status: number, data: string): MiniappAvatarAssetRead {
  let body: unknown
  try { body = JSON.parse(data) }
  catch { throw new ApiError('上传响应格式无效，结果尚未确认', 'protocol', status) }
  if (!body || typeof body !== 'object' || !('code' in body) || typeof body.code !== 'string' || !('message' in body) || typeof body.message !== 'string' || !('request_id' in body) || typeof body.request_id !== 'string') throw new ApiError('上传响应格式无效，结果尚未确认', 'protocol', status)
  if (status < 200 || status >= 300) throw new ApiError(body.message, 'http', status, body.code, body.request_id)
  if (body.code !== 'OK') throw new ApiError(body.message, 'business', status, body.code, body.request_id)
  if (!('data' in body) || !body.data || typeof body.data !== 'object' || !('id' in body.data) || typeof body.data.id !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(body.data.id) || !('url' in body.data) || typeof body.data.url !== 'string' || !body.data.url) throw new ApiError('上传响应缺少有效资产，勿确认头像已保存', 'protocol', status)
  return { id: body.data.id, url: body.data.url }
}

export function uploadAvatar(filePath: string, accessToken: string, signal: RequestSignal): Promise<MiniappAvatarAssetRead> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new ApiError('上传已取消，结果尚未确认', 'protocol')); return }
    const task = Taro.uploadFile({
      url: `${__API_BASE_URL__}/api/v1/miniapp/me/avatar-assets`, filePath, name: 'file', timeout: 20_000,
      header: { Accept: 'application/json', Authorization: `Bearer ${accessToken}` },
      success(response) {
        try { resolve(parseAvatarUpload(response.statusCode, response.data)) }
        catch (error) { reject(error) }
      },
      fail() { reject(new ApiError(signal.aborted ? '上传已取消，结果尚未确认' : '头像上传未确认，请检查网络', signal.aborted ? 'protocol' : 'network')) },
      complete() { signal.removeEventListener('abort', abort) },
    })
    function abort() { task.abort() }
    signal.addEventListener('abort', abort, { once: true })
  })
}
