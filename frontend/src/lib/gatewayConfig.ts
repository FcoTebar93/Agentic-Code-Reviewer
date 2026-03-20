export function getGatewayHttpBaseUrl(): string {
  return import.meta.env.VITE_GATEWAY_HTTP_URL ?? "http://localhost:8080";
}

export function getGatewayWsUrl(): string {
  return import.meta.env.VITE_GATEWAY_WS_URL ?? "ws://localhost:8080/ws";
}

export function gatewayHttpUrl(path: string): string {
  const base = getGatewayHttpBaseUrl().replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}
