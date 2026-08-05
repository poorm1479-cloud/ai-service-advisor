"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

export function ApiHealthCard() {
  const [status, setStatus] = useState<"loading" | "ok" | "down">("loading");
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const apiUrl = getApiUrl();
    (async () => {
      try {
        const res = await fetch(`${apiUrl}/health`);
        const data = await res.json();
        if (cancelled) return;
        if (res.ok && data.status === "ok") {
          setStatus("ok");
          setDetail(`phase ${data.phase ?? "?"}`);
        } else {
          setStatus("down");
          setDetail("unexpected response");
        }
      } catch {
        if (!cancelled) {
          setStatus("down");
          setDetail(`cannot reach ${apiUrl}`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="surface-panel p-4">
      <p className="font-display text-sm font-semibold tracking-tight">API health</p>
      <p className="mt-2 text-sm text-[var(--muted)]">
        {status === "loading" && "Checking FastAPI…"}
        {status === "ok" && `Connected (${detail})`}
        {status === "down" && `Unavailable — ${detail}`}
      </p>
    </div>
  );
}
