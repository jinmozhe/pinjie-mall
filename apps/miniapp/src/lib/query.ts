import { QueryClient } from '@tanstack/react-query'
import { ApiError } from './api'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: (count, error) => count < 1 && error instanceof ApiError && error.retryable,
      retryDelay: (_, error) => error instanceof ApiError ? Math.max(1000, error.retryAfter) : 1000,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
    },
    mutations: { retry: false, networkMode: 'always' },
  },
})
