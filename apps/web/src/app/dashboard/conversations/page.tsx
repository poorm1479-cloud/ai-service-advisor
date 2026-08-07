"use client";

import dynamic from "next/dynamic";
import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

const panelFallback = (
  <p className="text-sm text-[var(--muted)]">Loading panel…</p>
);

const SmsInboxPanel = dynamic(
  () =>
    import("@/components/conversations/SmsInboxPanel").then((m) => ({
      default: m.SmsInboxPanel,
    })),
  { loading: () => panelFallback, ssr: false },
);
const VoiceCallsPanel = dynamic(
  () =>
    import("@/components/conversations/VoiceCallsPanel").then((m) => ({
      default: m.VoiceCallsPanel,
    })),
  { loading: () => panelFallback, ssr: false },
);
const VoiceNotesPanel = dynamic(
  () =>
    import("@/components/conversations/VoiceNotesPanel").then((m) => ({
      default: m.VoiceNotesPanel,
    })),
  { loading: () => panelFallback, ssr: false },
);

const TABS = [
  { id: "sms", label: "SMS" },
  { id: "calls", label: "Calls" },
  { id: "notes", label: "Voice Notes" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function parseTab(value: string | null): TabId {
  if (value === "calls" || value === "notes" || value === "sms") return value;
  return "sms";
}

function ConversationsContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<TabId>(() => parseTab(searchParams.get("tab")));

  useEffect(() => {
    setTab(parseTab(searchParams.get("tab")));
  }, [searchParams]);

  const selectTab = useCallback(
    (next: TabId) => {
      setTab(next);
      const params = new URLSearchParams(searchParams.toString());
      params.set("tab", next);
      // Selection is tab-specific (SMS conversation id vs voice call id).
      params.delete("id");
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Conversations</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => selectTab(t.id)}
              className={`rounded-md border px-3 py-2 text-sm ${
                tab === t.id
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-[var(--line)] text-[var(--muted)]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {tab === "sms" && <SmsInboxPanel />}
        {tab === "calls" && <VoiceCallsPanel />}
        {tab === "notes" && <VoiceNotesPanel />}
      </div>
    </div>
  );
}

export default function ConversationsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-[var(--muted)]">Loading conversations…</p>}>
      <ConversationsContent />
    </Suspense>
  );
}
