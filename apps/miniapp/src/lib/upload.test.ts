import { beforeEach, describe, expect, it, vi } from 'vitest'
import Taro from '@tarojs/taro'
import { requestController } from './cancellation'
import { parseAvatarUpload, uploadAvatar } from './upload'

vi.mock('@tarojs/taro', () => ({ default: { uploadFile: vi.fn() } }))
const asset = { id: '00000000-0000-4000-8000-000000000001', url: 'https://assets.example.test/avatar.png' }
const envelope = (data: unknown = asset, code = 'OK') => JSON.stringify({ code, message: 'message', request_id: 'request', data })

describe('native avatar upload', () => {
  beforeEach(() => { vi.clearAllMocks() })
  it('parses the string response and refuses HTTP, business, malformed and invalid asset responses', () => {
    expect(parseAvatarUpload(201, envelope())).toEqual(asset)
    expect(() => parseAvatarUpload(403, envelope(null, 'PERMISSION_DENIED'))).toThrow()
    expect(() => parseAvatarUpload(200, envelope(null, 'STATE_CONFLICT'))).toThrow()
    for (const data of ['<html>', '{}', envelope({ id: 'invalid', url: asset.url }), envelope({ ...asset, url: '' })]) expect(() => parseAvatarUpload(200, data)).toThrow()
  })
  it('uses bearer multipart without JSON content type and aborts without automatic retransmission', async () => {
    const abort = vi.fn()
    let options!: Parameters<typeof Taro.uploadFile>[0]
    vi.mocked(Taro.uploadFile).mockImplementation((value) => {
      options = value
      return Object.assign(new Promise<Taro.uploadFile.SuccessCallbackResult>(() => {}), {
        abort, onHeadersReceived: vi.fn(), offHeadersReceived: vi.fn(), onProgressUpdate: vi.fn(), offProgressUpdate: vi.fn(), headersReceive: vi.fn(), progress: vi.fn(),
      })
    })
    const controller = requestController()
    const result = uploadAvatar('/tmp/avatar.png', 'access', controller.signal)
    expect(options.name).toBe('file')
    expect(options.header).toEqual({ Accept: 'application/json', Authorization: 'Bearer access' })
    controller.abort()
    expect(abort).toHaveBeenCalledTimes(1)
    options.fail?.({ errMsg: 'aborted' })
    options.complete?.({ errMsg: 'aborted' })
    await expect(result).rejects.toThrow('上传已取消')
    expect(Taro.uploadFile).toHaveBeenCalledTimes(1)
  })
  it('does not start an already cancelled upload', async () => {
    const controller = requestController(); controller.abort()
    await expect(uploadAvatar('/tmp/avatar.png', 'access', controller.signal)).rejects.toThrow('上传已取消')
    expect(Taro.uploadFile).not.toHaveBeenCalled()
  })
})
