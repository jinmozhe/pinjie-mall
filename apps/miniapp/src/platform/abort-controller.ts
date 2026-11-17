// The package's browser entry only re-exports native globals. Import the actual
// implementation so the WeChat bundle also works without DOM cancellation APIs.
import { AbortController as PolyfillController, AbortSignal as PolyfillSignal } from 'abort-controller/dist/abort-controller'

// ProvidePlugin resolves free references in dependencies (including Query) to
// these exports. Do not mutate the WeChat global object or replace native APIs.
export const RuntimeAbortController = typeof globalThis.AbortController === 'function'
  ? globalThis.AbortController : PolyfillController
export const RuntimeAbortSignal = typeof globalThis.AbortSignal === 'function'
  ? globalThis.AbortSignal : PolyfillSignal
