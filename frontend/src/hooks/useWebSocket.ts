import { useEffect, useRef, useState, useCallback } from "react";
import { type BaseEvent, type PrApproval, type WsMessage, parseBaseEvent } from "../types/events";

const MAX_EVENTS = 100;
const RECONNECT_DELAY_MS = 3000;

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

export function useWebSocket(url: string) {
  const [events, setEvents] = useState<BaseEvent[]>([]);
  const [pendingApprovals, setPendingApprovals] = useState<PrApproval[]>([]);
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
          const evt = parseBaseEvent(parsed.event);
          if (!evt) return;
          setEvents((prev) => {
            const next = [evt, ...prev];
            return next.slice(0, MAX_EVENTS);
          });
        } else if (parsed.type === "history") {
          const evt = parseBaseEvent(parsed.event);
          if (!evt) return;
          setEvents((prev) => {
            if (prev.some((e) => e.event_id === evt.event_id)) return prev;
            return [...prev, evt];
          });
        } else if (parsed.type === "approval") {
          setPendingApprovals((prev) => {
            if (prev.some((a) => a.approval_id === parsed.approval.approval_id))
              return prev;
            return [parsed.approval, ...prev];
          });
        } else if (parsed.type === "approval_decided") {
          setPendingApprovals((prev) =>
            prev.filter((a) => a.approval_id !== parsed.approval.approval_id)
          );
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

  return { events, pendingApprovals, status };
}
