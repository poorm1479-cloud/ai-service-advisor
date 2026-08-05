"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { SmsInboxPanel } from "@/components/conversations/SmsInboxPanel";
import { VoiceCallsPanel } from "@/components/conversations/VoiceCallsPanel";
import { VoiceNotesPanel } from "@/components/conversations/VoiceNotesPanel";

const TABS = [
  { id: "sms", label: "SMS" },
  { id: "calls", label: "Voice Calls" },
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
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Conversations</h1>
          <p className="text-sm text-[var(--muted)]">
            SMS inbox, voice calls, and mechanic voice notes in one place.
          </p>
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

      {tab === "sms" && <SmsInboxPanel />}
      {tab === "calls" && <VoiceCallsPanel />}
      {tab === "notes" && <VoiceNotesPanel />}
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
