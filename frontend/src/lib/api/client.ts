/**
 * Minimal API client.
 *
 * - Same-origin only (`/api/v1`): nginx (production) and the Vite dev proxy route
 *   it to the backend, so no API host or secret is ever embedded in the bundle.
 * - `credentials: "same-origin"` so the server-side session cookie (Phase 2) is
 *   sent; the frontend never stores tokens in JavaScript-readable storage.
 * - Errors are normalised from the backend envelope into ApiError.
 */

export const API_BASE = "/api/v1";

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

async function parseJson(response: Response): Promise<unknown> {
  const type = response.headers.get("content-type") ?? "";
  if (!type.includes("application/json")) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function apiGet<T>(path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      signal: options.signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "The server could not be reached. Check your network connection.", null);
  }

  const body = await parseJson(response);
  if (response.ok || options.acceptStatuses?.includes(response.status)) {
    if (body === null) {
      throw new ApiError(response.status, "invalid_response", "The server returned an unexpected response.", response.headers.get("x-request-id"));
    }
    return { status: response.status, data: body as T };
  }

  const envelope = (body as ApiErrorBody | null)?.error;
  throw new ApiError(
    response.status,
    envelope?.code ?? "http_error",
    envelope?.message ?? `The request failed (HTTP ${response.status}).`,
    envelope?.request_id ?? response.headers.get("x-request-id"),
    envelope?.details ?? [],
  );
}
