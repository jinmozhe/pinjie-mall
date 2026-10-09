// WeChat has no required DOM AbortController; adapt Query signals and native RequestTask.abort.
export type RequestSignal = {
  readonly aborted: boolean
  addEventListener(type: 'abort', listener: () => void, options?: { once?: boolean }): void
  removeEventListener(type: 'abort', listener: () => void): void
}
export function requestController() {
  let aborted = false
  const listeners = new Set<() => void>()
  const signal: RequestSignal = {
    get aborted() { return aborted },
    addEventListener(_, listener) { listeners.add(listener) },
    removeEventListener(_, listener) { listeners.delete(listener) },
  }
  return { signal, abort() { if (aborted) return; aborted = true; listeners.forEach((listener) => listener()); listeners.clear() } }
}
