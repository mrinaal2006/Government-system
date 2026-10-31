/**
 * API client.
 *
 * - Same-origin only (`/api/v1`); no API host or secret is embedded in the bundle.
 * - Session is an HttpOnly cookie; JavaScript never sees it. Unsafe requests echo
 *   the readable CSRF cookie in `X-CSRF-Token` (double-submit, validated server-side
 *   against the session).
 * - Errors are normalised from the backend envelope into ApiError.
 */

export const API_BASE = "/api/v1";
const CSRF_COOKIE = "dgi_csrf";
/** The citizen portal has its own session and CSRF cookie. */
const CITIZEN_CSRF_COOKIE = "dgi_ccsrf";

export interface ApiErrorBody {
  error?: { code?: string; message?: string; request_id?: string | null; details?: unknown[] };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: unknown[];

  constructor(status: number, code: string, message: string, requestId: string | null, details: unknown[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

export interface RequestOptions {
  signal?: AbortSignal;
  /** Non-2xx statuses whose JSON body is a valid result (e.g. 503 from readiness). */
  acceptStatuses?: number[];
}

export interface ApiResult<T> {
  status: number;
  data: T;
}

type Listener = (error: ApiError) => void;
const authListeners = new Set<Listener>();
/** Notified when the server says the session is missing/expired or needs another step. */
export function onAuthError(listener: Listener): () => void {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
}

export function readCookie(name: string): string {
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : "";
}

async function parseJson(response: Response): Promise<unknown> {
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export function toQuery(params: Record<string, unknown> | undefined): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    if (Array.isArray(value)) value.forEach((v) => q.append(key, String(v)));
    else q.append(key, String(value));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

async function request<T>(method: string, path: string, body: unknown, options: RequestOptions = {}): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET" && method !== "HEAD") headers["X-CSRF-Token"] = readCookie(path.startsWith("/citizen/") ? CITIZEN_CSRF_COOKIE : CSRF_COOKIE);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { method, credentials: "same-origin", headers, body: payload, signal: options.signal });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "The server could not be reached. Check your network connection.", null);
  }
  if (response.status === 204) return { status: 204, data: null as T };
  const json = await parseJson(response);
  if (response.ok || options.acceptStatuses?.includes(response.status)) {
    if (json === null) {
      throw new ApiError(response.status, "invalid_response", "The server returned an unexpected response.", response.headers.get("x-request-id"));
    }
    return { status: response.status, data: json as T };
  }
  const envelope = (json as ApiErrorBody | null)?.error;
  const error = new ApiError(
    response.status,
    envelope?.code ?? "http_error",
    envelope?.message ?? `The request failed (HTTP ${response.status}).`,
    envelope?.request_id ?? response.headers.get("x-request-id"),
    envelope?.details ?? [],
  );
  const isAuthCall = path.startsWith("/auth/") || path.startsWith("/citizen/");
  if (!isAuthCall && (error.code === "not_authenticated" || error.code === "additional_step_required")) {
    authListeners.forEach((l) => l(error));
  }
  throw error;
}

export function apiGet<T>(path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  return request<T>("GET", path, undefined, options);
}

export async function apiSend<T>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  return (await request<T>(method, path, body)).data;
}

export async function getJson<T>(path: string, params?: Record<string, unknown>, signal?: AbortSignal): Promise<T> {
  return (await apiGet<T>(`${path}${toQuery(params)}`, { signal })).data;
}

/** Human-readable message for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Something went wrong. Please try again.";
}

export function fieldErrors(error: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (error instanceof ApiError && error.code === "validation_error") {
    for (const d of error.details as Array<{ location?: string[]; message?: string }>) {
      const key = (d.location ?? []).filter((p) => p !== "body").join(".");
      if (key && d.message) out[key] = d.message.replace(/^Value error, /, "");
    }
  }
  return out;
}
