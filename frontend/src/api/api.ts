import { gatewayHttpUrl } from "../lib/gatewayConfig";

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

async function errorMessageFromResponse(resp: Response, bodyText: string): Promise<string> {
  if (bodyText) {
    try {
      const j = JSON.parse(bodyText) as { error?: string; detail?: string };
      if (typeof j.error === "string" && j.error) return j.error;
      if (typeof j.detail === "string" && j.detail) return j.detail;
    } catch {
      /* use raw text below */
    }
    return `${resp.status}: ${bodyText}`;
  }
  return `HTTP ${resp.status}`;
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(resolveUrl(path), { ...init, method: init?.method ?? "GET" });
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
  const headers = new Headers(init?.headers);
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
  const r = await fetch(resolveUrl(path), { method: "POST" });
  const bodyText = r.ok ? "" : await r.text();
  if (!r.ok) {
    throw new GatewayHttpError(
      bodyText ? `${r.status}: ${bodyText}` : `HTTP ${r.status}`,
      r.status,
      bodyText,
    );
  }
}
