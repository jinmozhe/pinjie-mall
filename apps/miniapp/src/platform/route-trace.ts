// Taro 4.3 does not declare these WeChat route APIs. Keep the native boundary local.
interface RouteEvent {
  path: string
  openType: string
  notFound?: boolean
}

type RouteListener = (event: RouteEvent) => void

declare const wx: {
  onAppRoute?: (listener: RouteListener) => void
  offAppRoute?: (listener: RouteListener) => void
}

let removeListener: (() => void) | undefined

export function stopRouteTrace(): void {
  removeListener?.()
  removeListener = undefined
}

export function startRouteTrace(launchPath: string): void {
  if (!__ROUTE_TRACE_ENABLED__) return
  stopRouteTrace()

  let sequence = 0
  let previousPath = '(启动)'
  function record(openType: string, path: string, notFound = false): void {
    // Do not retain event/query objects or log URL parameters, even in development.
    const target = path.split(/[?#]/, 1)[0] || '(未提供路径)'
    console.info('[路由轨迹]', JSON.stringify({
      序号: ++sequence,
      时间: new Date().toLocaleTimeString(),
      跳转方式: openType,
      来源页面: previousPath,
      目标页面: target,
      页面未找到: notFound,
    }))
    if (!notFound) previousPath = target
  }

  record('启动入口', launchPath)
  if (typeof wx === 'undefined' || typeof wx.onAppRoute !== 'function' || typeof wx.offAppRoute !== 'function') {
    console.warn('[路由轨迹] 当前环境不支持路由监听，仅记录启动入口；请使用支持路由事件的微信基础库（3.5.5 或以上）。')
    return
  }

  const listener: RouteListener = (event) => record(event.openType, event.path, event.notFound)
  const offAppRoute = wx.offAppRoute
  wx.onAppRoute(listener)
  removeListener = () => offAppRoute.call(wx, listener)
}
