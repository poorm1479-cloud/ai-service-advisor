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

function IconPhone({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.81.36 1.6.68 2.35a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.75.32 1.54.55 2.35.68A2 2 0 0 1 22 16.92Z" />
    </svg>
  );
}

function ConversationsContent() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div className="flex items-center gap-2">
          <IconPhone className="h-5 w-5 shrink-0 text-[var(--muted)]" />
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
