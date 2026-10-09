import Taro from '@tarojs/taro'
import type { ResponseModelListCategoryRead } from '@pinjie/api-client'
import { requestController } from './cancellation'
import type { RequestSignal } from './cancellation'

export type Envelope = Pick<ResponseModelListCategoryRead, 'code' | 'message' | 'request_id'> & { data: unknown }

export class ApiError extends Error {
  constructor(message: string, readonly kind: 'network' | 'http' | 'business' | 'protocol', readonly status = 0, readonly code = '', readonly requestId = '', readonly retryAfter = 0) {
    super(message)
    this.name = 'ApiError'
  }
  get retryable() { return (this.kind === 'network' || [429, 502, 503, 504].includes(this.status)) && this.retryAfter <= 60_000 }
}

export function getPublic<R extends Envelope>(path: string, signal?: RequestSignal): Promise<R['data']> {
  return request<R>(path, { signal })
}

export function request<R extends Envelope>(path: string, options: { signal?: RequestSignal; method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'; data?: object; accessToken?: string } = {}): Promise<R['data']> {
  const signal = options.signal ?? requestController().signal
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(new ApiError('请求已取消', 'protocol')); return }
    const task = Taro.request<R | Pick<ResponseModelListCategoryRead, 'code' | 'message' | 'request_id'>>({
      url: `${__API_BASE_URL__}/api/v1${path}`,
      method: options.method ?? 'GET',
      data: options.data,
      timeout: 12_000,
      header: { Accept: 'application/json', 'Content-Type': 'application/json', ...(options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : {}) },
      success(response) {
        const body = response.data
        const header = Object.entries(response.header).find(([key]) => key.toLowerCase() === 'retry-after')?.[1]
        const delay = typeof header === 'string' ? (/^\d+$/.test(header) ? Number(header) * 1000 : Math.max(0, Date.parse(header) - Date.now())) : 0
        const validEnvelope = body && typeof body === 'object' && typeof body.code === 'string' && typeof body.request_id === 'string' && typeof body.message === 'string'
        if (response.statusCode < 200 || response.statusCode >= 300) {
          reject(new ApiError(validEnvelope ? body.message : '服务请求失败，请重试', 'http', response.statusCode, validEnvelope ? body.code : '', validEnvelope ? body.request_id : '', Number.isFinite(delay) ? delay : 0)); return
        }
        if (!validEnvelope) { reject(new ApiError('服务响应格式无效，请重试', 'protocol', response.statusCode)); return }
        if (body.code !== 'OK') { reject(new ApiError(body.message, 'business', response.statusCode, body.code, body.request_id)); return }
        if (!('data' in body)) { reject(new ApiError('服务响应缺少数据', 'protocol')); return }
        resolve(body.data)
      },
      fail() { reject(new ApiError(signal.aborted ? '请求已取消' : '网络连接失败，请检查网络后重试', signal.aborted ? 'protocol' : 'network')) },
      complete() { signal.removeEventListener('abort', abort) },
    })
    function abort() { task.abort() }
    signal.addEventListener('abort', abort, { once: true })
  })
}
