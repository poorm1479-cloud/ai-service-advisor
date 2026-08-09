"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const panelFallback = (
  <div className="surface-panel flex min-h-0 flex-1 flex-col overflow-hidden">
    <div className="space-y-3 px-4 py-5">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex animate-pulse gap-3 rounded-xl bg-[var(--background)]/70 p-3">
          <div className="h-10 w-10 rounded-full bg-[var(--panel)]" />
          <div className="min-w-0 flex-1 space-y-2 py-1">
            <div className="h-3 w-2/3 rounded bg-[var(--panel)]" />
            <div className="h-2.5 w-1/2 rounded bg-[var(--panel)]" />
          </div>
        </div>
      ))}
    </div>
  </div>
);

const VoiceCallsPanel = dynamic(
  () =>
    import("@/components/conversations/VoiceCallsPanel").then((m) => ({
      default: m.VoiceCallsPanel,
    })),
  { loading: () => panelFallback, ssr: false },
);

function ConversationsContent() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Conversations</h1>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <VoiceCallsPanel />
      </div>
    </div>
  );
}

export default function ConversationsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
          <div className="h-8 w-48 animate-pulse rounded-md bg-[var(--panel)]" />
          {panelFallback}
        </div>
      }
    >
      <ConversationsContent />
    </Suspense>
  );
}
