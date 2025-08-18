import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE } from "../lib/api";

const RealtimeCtx = createContext(null);

/**
 * Centralizes the single WebSocket connection.
 * Consumers call: const rt = useRealtime();
 * rt.on("ticks", cb) to receive { seq, ts, data }.
 */
export default function RealtimeProvider({ children }) {
  const target = useRef(new EventTarget());
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    let ws;
    let stop = false;

    const connect = () => {
      if (stop) return;
      try {
        const wsUrl = API_BASE.replace(/^http/, "ws") + "/ws";
        ws = new WebSocket(wsUrl);
        ws.onopen = () => setConnected(true);
        ws.onclose = () => {
          setConnected(false);
          if (!stop) setTimeout(connect, 1500);
        };
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            const evt = new CustomEvent(msg.stream, { detail: msg });
            target.current.dispatchEvent(evt);
          } catch {}
        };
      } catch {
        if (!stop) setTimeout(connect, 1500);
      }
    };

    connect();
    return () => {
      stop = true;
      try { ws && ws.close(); } catch {}
    };
  }, []);

  const api = useMemo(
    () => ({
      connected,
      on: (eventName, handler) => {
        const h = (e) => handler(e.detail);
        target.current.addEventListener(eventName, h);
        return () => target.current.removeEventListener(eventName, h);
      },
    }),
    [connected]
  );

  return <RealtimeCtx.Provider value={api}>{children}</RealtimeCtx.Provider>;
}

export function useRealtime() {
  const ctx = useContext(RealtimeCtx);
  if (!ctx) throw new Error("useRealtime must be used within <RealtimeProvider>");
  return ctx;
}
