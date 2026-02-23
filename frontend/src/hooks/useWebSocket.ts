import { useEffect, useRef, useState, useCallback } from "react";
import type { BaseEvent, WsMessage } from "../types/events";

const MAX_EVENTS = 100;
const RECONNECT_DELAY_MS = 3000;

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export function useWebSocket(url: string) {
  const [events, setEvents] = useState<BaseEvent[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    setStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setStatus("connected");
    };

    ws.onmessage = (msg) => {
      if (!mountedRef.current) return;
      try {
        const parsed: WsMessage = JSON.parse(msg.data);

        if (parsed.type === "event") {
          setEvents((prev) => {
            const next = [parsed.event, ...prev];
            return next.slice(0, MAX_EVENTS);
          });
        } else if (parsed.type === "history") {
          // History events arrive individually at connection time
          setEvents((prev) => {
            const evt = parsed.event as unknown as BaseEvent;
            // Avoid duplicates from history
            if (prev.some((e) => e.event_id === evt.event_id)) return prev;
            return [...prev, evt];
          });
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus("disconnected");
      wsRef.current = null;
      // Auto-reconnect
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };
  }, [url]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { events, status };
}
