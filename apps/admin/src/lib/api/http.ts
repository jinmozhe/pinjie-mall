type ApiEnvelope<T> = {
  code: string;
  message: string;
  data: T;
  request_id: string;
};

type ApiErrorBody = {
  code?: string;
  message?: string;
  request_id?: string;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId?: string,
    public readonly retryAfter?: string,
    public readonly source: "request" | "refresh" = "request",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE = (process.env.VITE_API_URL || window.location.origin).replace(/\/$/, "");
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const AUTH_RETRY_EXCLUDED = new Set([
  "/api/v1/admin/auth/login",
  "/api/v1/admin/auth/refresh",
  "/api/v1/admin/auth/logout",
]);
const SESSION_ERROR_CODES = new Set([
  "AUTH_REQUIRED", "AUTH_TOKEN_INVALID", "AUTH_SESSION_REVOKED",
  "AUTH_SESSION_EXPIRED", "AUTH_REFRESH_REUSE_DETECTED",
]);

export function isSessionError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status === 401 && SESSION_ERROR_CODES.has(error.code);
}

let refreshPromise: Promise<void> | null = null;
let sessionExpiredHandler: (() => void) | undefined;

export function setSessionExpiredHandler(handler: (() => void) | undefined): void {
  sessionExpiredHandler = handler;
}

function reportSessionExpired(error: unknown): void {
  if (isSessionError(error)) sessionExpiredHandler?.();
}

function readCookie(name: string): string | undefined {
  const prefix = `${encodeURIComponent(name)}=`;
  const item = document.cookie.split("; ").find((value) => value.startsWith(prefix));
  return item ? decodeURIComponent(item.slice(prefix.length)) : undefined;
}

async function parseError(response: Response, source: ApiError["source"] = "request"): Promise<ApiError> {
  let body: ApiErrorBody = {};
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = {};
  }
  return new ApiError(
    response.status,
    body.code ?? "REQUEST_FAILED",
    body.message ?? "请求未完成，请稍后重试",
    body.request_id,
    response.headers.get("retry-after") ?? undefined,
    source,
  );
}

async function refreshSession(): Promise<void> {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const csrf = readCookie("pinjie_admin_csrf");
      const response = await fetch(`${API_BASE}/api/v1/admin/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: csrf ? { "X-CSRF-Token": csrf } : undefined,
      });
      if (!response.ok) throw await parseError(response, "refresh");
    })().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  options: { retryAuth?: boolean } = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const isFormData = typeof globalThis.FormData !== "undefined" && init.body instanceof globalThis.FormData;
  if (init.body && !isFormData && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie("pinjie_admin_csrf");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, method, headers, credentials: "include" });
  if (!response.ok) {
    const error = await parseError(response);
    if (isSessionError(error) && options.retryAuth !== false && !AUTH_RETRY_EXCLUDED.has(path)) {
      try {
        await refreshSession();
      } catch (refreshError) {
        reportSessionExpired(refreshError);
        throw refreshError;
      }
      return apiRequest<T>(path, init, { ...options, retryAuth: false });
    }
    if (path !== "/api/v1/admin/auth/login") reportSessionExpired(error);
    throw error;
  }
  const payload = (await response.json()) as ApiEnvelope<T>;
  return payload.data;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求未完成，请稍后重试";
}
