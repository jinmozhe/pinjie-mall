import { useSyncExternalStore } from 'react'
import Taro from '@tarojs/taro'
import type { ConsumerSessionRead, ConsumerUserRead, ResponseModelConsumerSessionRead, ResponseModelConsumerCapabilitiesRead, ResponseModelConsumerUserRead, ResponseModelNoneType } from '@pinjie/api-client'
import { ApiError, request } from './api'
import type { Envelope } from './api'
import { queryClient } from './query'
import { requestController } from './cancellation'
import type { RequestSignal } from './cancellation'
import { uploadAvatar } from './upload'
import { clearAuthIntent } from './auth-navigation'

type Snapshot = { user: ConsumerUserRead | null; epoch: number; busy: boolean; error: string }
type LoginResult = { user: ConsumerUserRead; epoch: number }
let snapshot: Snapshot = { user: null, epoch: 0, busy: false, error: '' }
let credentials: ConsumerSessionRead | null = null
let loggingIn: { epoch: number; promise: Promise<LoginResult> } | null = null
let loggingOut = false
let refreshing: Promise<void> | null = null
const listeners = new Set<() => void>()
const pending = new Set<ReturnType<typeof requestController>>()
function emit(patch: Partial<Snapshot>) { snapshot = { ...snapshot, ...patch }; listeners.forEach((listener) => listener()) }
function clear(error = '') {
  credentials = null
  pending.forEach((controller) => controller.abort())
  pending.clear()
  void queryClient.cancelQueries({ queryKey: ['private'] })
  queryClient.removeQueries({ queryKey: ['private'] })
  Taro.removeTabBarBadge({ index: 2 }).catch(() => { /* The tab bar may not be mounted yet. */ })
  emit({ user: null, epoch: snapshot.epoch + 1, busy: false, error })
}
export function useSession() { return useSyncExternalStore((listener) => { listeners.add(listener); return () => listeners.delete(listener) }, () => snapshot) }
export function sessionScope() { return snapshot.epoch }
export function signedIn() { return !!credentials }
export function phoneReady() { return !!credentials?.user.phone_bound }

export async function bindPhone(code: string) {
  const epoch = snapshot.epoch
  const user = await privateRequest<ResponseModelConsumerUserRead>('/users/me/phone', { method: 'POST', data: { code } })
  updateSessionUser(user, epoch)
  await queryClient.invalidateQueries({ queryKey: ['private', 'me', epoch] })
}

export async function login(): Promise<LoginResult> {
  if (loggingOut) throw new ApiError('正在退出，请稍后重新登录', 'protocol')
  if (credentials) return { user: credentials.user, epoch: snapshot.epoch }
  if (loggingIn?.epoch === snapshot.epoch) return loggingIn.promise
  clear()
  const epoch = snapshot.epoch
  emit({ busy: true })
  function assertCurrent() {
    if (epoch !== snapshot.epoch || loggingOut) throw new ApiError('会话已改变，请重新登录', 'protocol')
  }
  const flight = (async () => {
    try {
      const capability = await request<ResponseModelConsumerCapabilitiesRead>('/auth/capabilities')
      assertCurrent()
      if (!capability.login_enabled) throw new Error('微信登录尚未开放，可继续浏览商品')
      const wxResult = await Taro.login({ timeout: 8000 })
      assertCurrent()
      if (!wxResult.code) throw new Error('未取得微信登录凭证，请重新发起')
      const result = await request<ResponseModelConsumerSessionRead>('/auth/login', { method: 'POST', data: { code: wxResult.code } })
      assertCurrent()
      Taro.setStorageSync('pinjie.signed-out', false)
      credentials = result
      emit({ user: result.user, busy: false })
      return { user: result.user, epoch }
    } catch (error) {
      if (epoch === snapshot.epoch) emit({ busy: false, error: error instanceof Error ? error.message : '微信身份建立失败，可继续浏览或主动登录重试' })
      throw error
    }
  })()
  loggingIn = { epoch, promise: flight }
  try { return await flight }
  finally { if (loggingIn?.promise === flight) loggingIn = null }
}
export async function restoreSession() {
  try {
    if (Taro.getStorageSync('pinjie.signed-out') === true) return
  } catch {
    emit({ error: '无法确认退出偏好，请主动登录；公开浏览不受影响' })
    return
  }
  try { await login() }
  catch { /* login publishes current-session failures; background startup must not block public browsing. */ }
}
async function refresh() {
  if (refreshing) return refreshing
  const current = credentials
  const epoch = snapshot.epoch
  if (!current) throw new ApiError('请先登录', 'http', 401)
  const flight = (async () => {
    try {
      const result = await request<ResponseModelConsumerSessionRead>('/auth/refresh', { method: 'POST', data: { refresh_token: current.refresh_token } })
      if (epoch !== snapshot.epoch || result.user.id !== current.user.id || result.session_id !== current.session_id) throw new ApiError('会话已改变，请重新操作', 'protocol')
      credentials = result
      emit({ user: result.user })
    } catch (error) {
      if (epoch === snapshot.epoch) clear('会话刷新未完成，请主动重新登录')
      throw error
    }
  })()
  refreshing = flight
  try { await flight } finally { if (refreshing === flight) refreshing = null }
}
async function privateCall<T>(operation: (accessToken: string, signal: RequestSignal) => Promise<T>, signal?: RequestSignal): Promise<T> {
  const epoch = snapshot.epoch
  if (!credentials) throw new ApiError('请先登录', 'http', 401)
  if (Date.parse(credentials.access_expires_at) <= Date.now() + 30_000) await refresh()
  if (!credentials || epoch !== snapshot.epoch) throw new ApiError('会话已改变，请重新操作', 'protocol')
  const controller = requestController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) controller.abort()
  pending.add(controller)
  try {
    const result = await operation(credentials.access_token, controller.signal)
    if (epoch !== snapshot.epoch) throw new ApiError('会话已改变，请重新读取', 'protocol')
    return result
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.code === 'AUTH_ACCOUNT_DISABLED') && epoch === snapshot.epoch) clear('登录状态已失效，请重新登录')
    throw error
  } finally { pending.delete(controller); signal?.removeEventListener('abort', abort) }
}
export function privateRequest<R extends Envelope>(path: string, options: { signal?: RequestSignal; method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'; data?: object } = {}): Promise<R['data']> {
  return privateCall((accessToken, signal) => request<R>(path, { ...options, signal, accessToken }), options.signal)
}
export function privateAvatarUpload(filePath: string, signal?: RequestSignal) {
  return privateCall((accessToken, uploadSignal) => uploadAvatar(filePath, accessToken, uploadSignal), signal)
}
export function updateSessionUser(user: ConsumerUserRead, epoch: number) {
  if (!credentials || epoch !== snapshot.epoch || user.id !== credentials.user.id) throw new ApiError('会话已改变，请重新读取资料', 'protocol')
  credentials = { ...credentials, user }
  emit({ user })
}
export async function logout() {
  if (loggingOut) return
  loggingOut = true
  emit({ busy: true })
  clearAuthIntent()
  const epoch = snapshot.epoch
  let failure = ''
  try { Taro.setStorageSync('pinjie.signed-out', true) }
  catch { failure = '无法保存退出偏好，请检查本机存储；' }
  try {
    if (credentials) await privateRequest<ResponseModelNoneType>('/auth/logout', { method: 'POST' })
  } catch (error) { failure += error instanceof Error ? `服务端退出未确认：${error.message}` : '服务端退出未确认' }
  finally {
    if (epoch === snapshot.epoch) clear(failure)
    loggingOut = false
  }
}
