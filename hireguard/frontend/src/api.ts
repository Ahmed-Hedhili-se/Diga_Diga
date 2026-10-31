// Same-origin API client: session cookie + double-submit CSRF header on every mutation.

let csrfToken = "";
let lastActivity = Date.now();
let onSessionLost: ((reason: string) => void) | null = null;

export function setCsrf(token: string) {
  csrfToken = token;
}

/** Called once by AuthProvider: any 401 outside the login flow means the session is gone. */
export function setSessionLostHandler(fn: ((reason: string) => void) | null) {
  onSessionLost = fn;
}

/** Time of the last successful API call: the server's idle timer restarts on every request. */
export function lastApiActivity() {
  return lastActivity;
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfter: number | null = null) {
    super(message);
  }
}

type Opts = {
  method?: string;
  body?: unknown;
  form?: FormData;
  raw?: { data: BodyInit; type: string };
};

const AUTH_FLOW = new Set(["/auth/login", "/auth/me"]);

async function request(path: string, opts: Opts = {}): Promise<Response> {
  const hasBody = opts.body !== undefined || opts.form !== undefined || opts.raw !== undefined;
  const method = opts.method ?? (hasBody ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.raw) {
    headers["Content-Type"] = opts.raw.type;
    body = opts.raw.data;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body, credentials: "same-origin" });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* non-JSON error */
    }
    const retry = Number(res.headers.get("Retry-After"));
    if (res.status === 401 && !AUTH_FLOW.has(path)) onSessionLost?.(msg);
    throw new ApiError(res.status, msg, Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  lastActivity = Date.now();
  return res;
}

export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const res = await request(path, opts);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export async function apiBlob(path: string): Promise<Blob> {
  return (await request(path)).blob();
}

export async function downloadFile(path: string, filename: string) {
  const blob = await apiBlob(path);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errMsg(e: unknown): string {
  if (e instanceof ApiError) return `${e.status}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}
