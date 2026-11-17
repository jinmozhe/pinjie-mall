import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Taro from '@tarojs/taro'
import { QueryClient, isCancelledError } from '@tanstack/react-query'
import { getPublic } from '../lib/api'
import type { Envelope } from '../lib/api'
import type { RequestSignal } from '../lib/cancellation'

vi.mock('@tarojs/taro', () => ({ default: { request: vi.fn() } }))

describe('WeChat query cancellation runtime', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
    vi.stubGlobal('__API_BASE_URL__', 'http://127.0.0.1:18168')
  })
  afterEach(() => { vi.unstubAllGlobals() })

  async function withoutNativeCancellation() {
    vi.stubGlobal('AbortController', undefined)
    vi.stubGlobal('AbortSignal', undefined)
    return import('./abort-controller')
  }

  it('preserves native constructors when available', async () => {
    const runtime = await import('./abort-controller')
    expect(runtime.RuntimeAbortController).toBe(globalThis.AbortController)
    expect(runtime.RuntimeAbortSignal).toBe(globalThis.AbortSignal)
  })

  it('supports abort state, once listeners, listener removal and repeated cancellation without DOM globals', async () => {
    const { RuntimeAbortController, RuntimeAbortSignal } = await withoutNativeCancellation()
    const controller = new RuntimeAbortController()
    const signal: RequestSignal = controller.signal
    const once = vi.fn()
    const removed = vi.fn()
    signal.addEventListener('abort', once, { once: true })
    signal.addEventListener('abort', removed)
    signal.removeEventListener('abort', removed)
    expect(controller.signal.aborted).toBe(false)
    expect(controller.signal).toBeInstanceOf(RuntimeAbortSignal)
    controller.abort()
    controller.abort()
    expect(controller.signal.aborted).toBe(true)
    expect(once).toHaveBeenCalledTimes(1)
    expect(removed).not.toHaveBeenCalled()
    expect(globalThis.AbortController).toBeUndefined()
  })

  it('starts Query requests, forwards cancellation to RequestTask.abort and allows a subsequent query', async () => {
    const { RuntimeAbortController } = await withoutNativeCancellation()
    // Vitest does not run Webpack's ProvidePlugin; give Query the same constructor.
    vi.stubGlobal('AbortController', RuntimeAbortController)
    let options!: Parameters<typeof Taro.request>[0]
    const abort = vi.fn(() => {
      options.fail?.({ errMsg: 'request:fail abort' })
      options.complete?.({ errMsg: 'request:fail abort' })
    })
    vi.mocked(Taro.request).mockImplementation((value) => {
      options = value
      return Object.assign(new Promise<Taro.request.SuccessCallbackResult>(() => {}), {
        abort, onHeadersReceived: vi.fn(), offHeadersReceived: vi.fn(),
        onChunkReceived: vi.fn(), offChunkReceived: vi.fn(),
      })
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    try {
      const queryKey = ['catalog', 'categories']
      const pending = client.fetchQuery({ queryKey, queryFn: ({ signal }) => getPublic<Envelope>('/product-categories', signal) })
      const cancelled = pending.catch((error: unknown) => error)
      expect(Taro.request).toHaveBeenCalledTimes(1)
      expect(options.url).toBe('http://127.0.0.1:18168/api/v1/product-categories')
      await client.cancelQueries({ queryKey })
      expect(isCancelledError(await cancelled)).toBe(true)
      expect(abort).toHaveBeenCalledTimes(1)
      expect(client.getQueryData(queryKey)).toBeUndefined()

      const next = client.fetchQuery({ queryKey, queryFn: ({ signal }) => getPublic<Envelope>('/product-categories', signal) })
      const response = { statusCode: 200, header: {}, cookies: [], errMsg: 'request:ok', data: { code: 'OK', message: 'ok', request_id: 'public-read', data: [] } }
      options.success?.(response)
      options.complete?.(response)
      await expect(next).resolves.toEqual([])
      await client.cancelQueries({ queryKey })
      expect(abort).toHaveBeenCalledTimes(1)
      expect(Taro.request).toHaveBeenCalledTimes(2)
    } finally { client.clear() }
  })
})
