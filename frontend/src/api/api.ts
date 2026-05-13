import { gatewayHttpUrl } from "../lib/gatewayConfig";
import i18n from "../i18n";

export class GatewayHttpError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly bodyText: string,
  ) {
    super(message);
    this.name = "GatewayHttpError";
  }
}

function resolveUrl(path: string): string {
  return path.startsWith("http") ? path : gatewayHttpUrl(path);
}

type ErrorPayload = {
  error?: string;
  detail?: string | { code?: string; message?: string; params?: Record<string, unknown> };
  message?: string;
  code?: string;
  params?: Record<string, unknown>;
};

function getLocaleHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept-Language")) {
    headers.set("Accept-Language", i18n.resolvedLanguage || i18n.language || "es");
  }
  return headers;
}

function translateErrorCode(
  code: string | undefined,
  params: Record<string, unknown> | undefined,
  fallback?: string,
): string | null {
  if (!code) return fallback ?? null;
  const key = `apiErrors.${code}`;
  if (i18n.exists(key)) {
    return i18n.t(key, {
      ...(params ?? {}),
      defaultValue: fallback ?? code,
    });
  }
  return fallback ?? code;
}

async function errorMessageFromResponse(resp: Response, bodyText: string): Promise<string> {
  if (bodyText) {
    try {
      const j = JSON.parse(bodyText) as ErrorPayload;
      if (typeof j.detail === "object" && j.detail !== null) {
        return (
          translateErrorCode(
            j.detail.code,
            j.detail.params,
            j.detail.message,
          ) ?? `${resp.status}`
        );
      }
      if (typeof j.message === "string" && j.message) {
        return translateErrorCode(j.code, j.params, j.message) ?? j.message;
      }
      if (typeof j.error === "string" && j.error) {
        return translateErrorCode(j.code, j.params, j.error) ?? j.error;
      }
      if (typeof j.detail === "string" && j.detail) {
        return translateErrorCode(j.code, j.params, j.detail) ?? j.detail;
      }
      const translated = translateErrorCode(j.code, j.params);
      if (translated) return translated;
    } catch {
      /* use raw text below */
    }
    return `${resp.status}: ${bodyText}`;
  }
  return `HTTP ${resp.status}`;
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(resolveUrl(path), {
    ...init,
    method: init?.method ?? "GET",
    headers: getLocaleHeaders(init),
  });
  if (!r.ok) {
    const bodyText = await r.text();
    throw new GatewayHttpError(
      await errorMessageFromResponse(r, bodyText),
      r.status,
      bodyText,
    );
  }
  return r.json() as Promise<T>;
}

export async function postJson<T>(
  path: string,
  body?: unknown,
  init?: Omit<RequestInit, "body" | "method">,
): Promise<T> {
  const headers = getLocaleHeaders(init);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const r = await fetch(resolveUrl(path), {
    ...init,
    method: "POST",
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const bodyText = await r.text();
  if (!r.ok) {
    throw new GatewayHttpError(
      await errorMessageFromResponse(r, bodyText),
      r.status,
      bodyText,
    );
  }
  if (!bodyText.trim()) return undefined as T;
  return JSON.parse(bodyText) as T;
}

export async function postWithoutBody(path: string): Promise<void> {
  const r = await fetch(resolveUrl(path), {
    method: "POST",
    headers: getLocaleHeaders(),
  });
  const bodyText = r.ok ? "" : await r.text();
  if (!r.ok) {
    throw new GatewayHttpError(
      bodyText
        ? await errorMessageFromResponse(r, bodyText)
        : `HTTP ${r.status}`,
      r.status,
      bodyText,
    );
  }
}
