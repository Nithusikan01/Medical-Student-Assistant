let accessToken: string | null = null;

// A single in-flight refresh shared by every caller. Without this, N requests
// failing with 401 at once would each rotate the refresh token, and rotation
// treats a replayed token as theft - logging the user out.
let refreshInFlight: Promise<string | null> | null = null;

let onAuthLost: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAuthLostHandler(handler: (() => void) | null): void {
  onAuthLost = handler;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readError(response: Response): Promise<string> {
  const fallback = `Request failed (${response.status})`;

  const body = await response.json().catch(() => null);

  if (!body) {
    return fallback;
  }

  if (typeof body.detail === "string") {
    return body.detail;
  }

  if (Array.isArray(body.detail)) {
    return body.detail
      .map((item: { msg?: string }) => item.msg ?? fallback)
      .join("; ");
  }

  return fallback;
}

async function refreshAccessToken(): Promise<string | null> {
  const response = await fetch("/api/auth/refresh", {
    method: "POST",
    credentials: "include",
  });

  if (!response.ok) {
    return null;
  }

  const body = await response.json();
  accessToken = body.access_token;

  return accessToken;
}

function refreshOnce(): Promise<string | null> {
  refreshInFlight ??= refreshAccessToken().finally(() => {
    refreshInFlight = null;
  });

  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  // Auth endpoints must never trigger a refresh retry: refreshing a failed
  // refresh would loop.
  skipRefresh?: boolean;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const send = async (): Promise<Response> => {
    const headers: Record<string, string> = {};

    if (accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    }

    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    return fetch(path, {
      method: options.method ?? "GET",
      headers,
      credentials: "include",
      body: options.formData ?? (
        options.body !== undefined ? JSON.stringify(options.body) : undefined
      ),
    });
  };

  let response = await send();

  if (response.status === 401 && !options.skipRefresh) {
    const renewed = await refreshOnce();

    if (renewed) {
      response = await send();
    } else {
      accessToken = null;
      onAuthLost?.();
      throw new ApiError("Your session has expired.", 401);
    }
  }

  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch("/health/health");
    return response.ok;
  } catch {
    return false;
  }
}

export { refreshOnce as attemptSilentRefresh };
