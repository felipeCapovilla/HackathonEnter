import { useEffect } from "react";
import { request } from "./api";

const FLUSH_MS = 30_000;
const IDLE_MS = 120_000;

// Tempo ativo do advogado no processo: só conta com a aba visível e com interação nos últimos 2 min.
// Envia em pacotes de até 5 min; o backend rejeita mais que isso por aviso.
export function useActiveTime(caseId, enabled) {
  useEffect(() => {
    if (!enabled || !caseId) return undefined;
    let last = Date.now();
    let lastInput = Date.now();
    let pending = 0;
    const touch = () => { lastInput = Date.now(); };
    const tick = () => {
      const now = Date.now();
      if (document.visibilityState === "visible" && now - lastInput < IDLE_MS) pending += (now - last) / 1000;
      last = now;
    };
    const flush = () => {
      tick();
      const seconds = Math.min(300, Math.floor(pending));
      if (seconds < 5) return;
      pending -= seconds;
      request(`/cases/${encodeURIComponent(caseId)}/engagement`, {
        method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
        body: JSON.stringify({ event_type: "ACTIVE_TIME", active_seconds: seconds }),
      }).catch(() => {});
    };
    const onVisibility = () => { if (document.visibilityState === "hidden") flush(); else last = Date.now(); };
    const inputs = ["pointermove", "keydown", "scroll", "click", "touchstart"];
    inputs.forEach((name) => window.addEventListener(name, touch, { passive: true }));
    document.addEventListener("visibilitychange", onVisibility);
    const timer = window.setInterval(flush, FLUSH_MS);
    return () => {
      window.clearInterval(timer);
      flush();
      inputs.forEach((name) => window.removeEventListener(name, touch));
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [caseId, enabled]);
}
