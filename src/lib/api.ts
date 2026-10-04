/**
 * RiskLens API Client
 * 
 * Features:
 * - Native fetch wrapper pointing to VITE_API_URL (default: http://localhost:8000)
 * - In-memory access token storage (mitigates XSS token leakage)
 * - Persistent refresh token in localStorage with rotation & reuse detection support
 * - Auto-refresh interceptor on 401 with concurrent request deduplication
 * - Automatic session revocation callback on refresh failure
 */

// Reference vite/client env types
const envObj = (import.meta as unknown as { env?: Record<string, string> })?.env;
const API_BASE = envObj?.VITE_API_URL || "http://localhost:8000";
const REFRESH_STORAGE_KEY = "risklens_refresh_token";

let inMemoryAccessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;
const authRevokedListeners = new Set<() => void>();

export class ApiError extends Error {
  status: number;
  code: string;
  field?: string;
  detail?: unknown;

  constructor(
    statusOrCode: number | string,
    message: string,
    codeOrField?: string,
    maybeField?: string,
    detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
    if (typeof statusOrCode === "number") {
      this.status = statusOrCode;
      this.code = codeOrField || `HTTP_${statusOrCode}`;
      this.field = maybeField;
      this.detail = detail;
    } else {
      this.status = 400;
      this.code = statusOrCode;
      this.field = codeOrField;
      this.detail = detail;
    }
  }
}

/**
 * Maps FastAPI detail arrays (both {field, message} and {loc, msg}) to a Record<field, message>.
 */
export function extractFieldErrors(detail: unknown): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!detail) return errors;

  if (Array.isArray(detail)) {
    for (const item of detail) {
      if (item && typeof item === "object") {
        const d = item as { field?: string; message?: string; loc?: Array<string | number>; msg?: string };
        if (d.field) {
          errors[d.field] = d.message || "Invalid value";
        } else if (d.loc && Array.isArray(d.loc) && d.loc.length > 0) {
          const fieldName = String(d.loc[d.loc.length - 1]);
          errors[fieldName] = d.msg || "Invalid value";
        }
      }
    }
  } else if (typeof detail === "object") {
    for (const [k, v] of Object.entries(detail as Record<string, unknown>)) {
      if (typeof v === "string") {
        errors[k] = v;
      }
    }
  }

  return errors;
}

export function onAuthRevoked(listener: () => void): () => void {
  authRevokedListeners.add(listener);
  return () => {
    authRevokedListeners.delete(listener);
  };
}

function notifyAuthRevoked(): void {
  inMemoryAccessToken = null;
  localStorage.removeItem(REFRESH_STORAGE_KEY);
  authRevokedListeners.forEach((fn) => fn());
}

export function getAccessToken(): string | null {
  return inMemoryAccessToken;
}

export function setAccessToken(token: string | null): void {
  inMemoryAccessToken = token;
}

export function getRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setRefreshToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(REFRESH_STORAGE_KEY, token);
    } else {
      localStorage.removeItem(REFRESH_STORAGE_KEY);
    }
  } catch {
    // Ignore storage quota or access errors
  }
}

export function parseJwtPayload(token: string): { sub?: string; exp?: number; [key: string]: unknown } {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return {};
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return JSON.parse(jsonPayload);
  } catch {
    return {};
  }
}

/**
 * Execute refresh token rotation once; deduplicates simultaneous calls.
 */
async function performTokenRefresh(): Promise<string | null> {
  const currentRefresh = getRefreshToken();
  if (!currentRefresh) {
    notifyAuthRevoked();
    return null;
  }

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: currentRefresh }),
    });

    if (!res.ok) {
      notifyAuthRevoked();
      return null;
    }

    const data = await res.json();
    const newAccess = data.access_token as string;
    const newRefresh = data.refresh_token as string;

    setAccessToken(newAccess);
    setRefreshToken(newRefresh);
    return newAccess;
  } catch {
    notifyAuthRevoked();
    return null;
  }
}

/**
 * Typed API request wrapper with 401 interceptor and retry.
 */
export async function apiRequest<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;

  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  if (inMemoryAccessToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${inMemoryAccessToken}`);
  }

  let response: Response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (netErr) {
    if (netErr instanceof Error && netErr.name === "AbortError") {
      throw netErr;
    }
    throw new ApiError(
      0,
      netErr instanceof Error ? netErr.message : "Network error: unable to connect to server.",
      "NETWORK_ERROR"
    );
  }

  // Auto-refresh interceptor on 401 (skip if the failing request is itself an auth refresh or login call)
  if (response.status === 401 && !path.includes("/auth/refresh") && !path.includes("/auth/login")) {
    if (!refreshPromise) {
      refreshPromise = performTokenRefresh().finally(() => {
        refreshPromise = null;
      });
    }

    const newAccessToken = await refreshPromise;
    if (newAccessToken) {
      // Retry original request with newly rotated access token
      const retryHeaders = new Headers(options.headers || {});
      if (!retryHeaders.has("Content-Type") && options.body && typeof options.body === "string") {
        retryHeaders.set("Content-Type", "application/json");
      }
      retryHeaders.set("Authorization", `Bearer ${newAccessToken}`);

      const retryRes = await fetch(url, { ...options, headers: retryHeaders });
      return handleResponse<T>(retryRes);
    }
  }

  return handleResponse<T>(response);
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return null as unknown as T;
  }

  const contentType = response.headers.get("content-type") || "";
  let payload: any = null;
  if (contentType.includes("application/json")) {
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
  } else {
    try {
      payload = await response.text();
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    let message = "Request failed.";
    let field: string | undefined;

    if (payload && typeof payload === "object") {
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (Array.isArray(payload.detail) && payload.detail.length > 0) {
        // FastAPI validation error format
        const firstErr = payload.detail[0];
        if (firstErr.message) {
          message = firstErr.message;
          field = firstErr.field;
        } else if (firstErr.msg) {
          message = firstErr.msg;
          if (Array.isArray(firstErr.loc) && firstErr.loc.length > 0) {
            field = String(firstErr.loc[firstErr.loc.length - 1]);
          }
        } else {
          message = "Validation error";
        }
      } else if (payload.message) {
        message = payload.message;
      }
    }

    throw new ApiError(response.status, message, `HTTP_${response.status}`, field, payload?.detail);
  }

  return payload as T;
}
