"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/lib/auth";
import {
  Campaign,
  SuggestedAction,
  createCampaign,
  getAiPreview,
  listSuggestedActions,
  type AiPreview,
  type AudienceMember,
} from "@/lib/marketing";

const STEPS = ["AI Recommendations", "Review customers", "AI message"] as const;
/** Drafts stay email for API compat — sending is disabled. */
const PREVIEW_CHANNELS = ["email"] as const;

function IconMarketing({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M4.5 12.5 19.5 5.5 13.5 19.5l-2-5.5-5.5-1.5Z" />
      <path d="M11.5 14 19.5 5.5" />
    </svg>
  );
}

function IconSpark({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3.5 13.4 8.6 18.5 10 13.4 11.4 12 16.5 10.6 11.4 5.5 10 10.6 8.6 12 3.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M18.5 15.5 19.2 17.8 21.5 18.5 19.2 19.2 18.5 21.5 17.8 19.2 15.5 18.5 17.8 17.8 18.5 15.5Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconUser({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="8" r="3.25" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M5.5 19.25c1.4-3 3.7-4.5 6.5-4.5s5.1 1.5 6.5 4.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconMail({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect
        x="3.75"
        y="5.75"
        width="16.5"
        height="12.5"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="m5 8 7 5 7-5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconArrow({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M5 12h12.5M13 6.5 18.5 12 13 17.5"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconX({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconCopy({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect
        x="9"
        y="9"
        width="11"
        height="11"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path
        d="M7 15H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v1"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconCheck({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="m5.5 12.5 4 4 9-9"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconClipboard({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect
        x="6"
        y="4.75"
        width="12"
        height="15.5"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M9 4.75h6v2.5H9z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path
        d="M9.5 11h5M9.5 14.5h3.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconUserOff({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="8" r="3.25" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M5.5 19.25c1.4-3 3.7-4.5 6.5-4.5s5.1 1.5 6.5 4.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="M4.5 4.5 19.5 19.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconWrench({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M14.7 6.3a4.2 4.2 0 0 0-5.9 5.9L4.5 16.5l3 3 4.3-4.3a4.2 4.2 0 0 0 5.9-5.9l-2.4 2.4-2.6-2.4 2-2.4Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconCalendarMissed({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect
        x="3.75"
        y="5.75"
        width="16.5"
        height="14.5"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M8 3.75v3.5M16 3.75v3.5M3.75 10.25h16.5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="m10 14.25 4 4M14 14.25l-4 4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function actionIcon(action: SuggestedAction) {
  const key = `${action.id} ${action.campaign_type}`.toLowerCase();
  const cls = "h-5 w-5";
  if (key.includes("declined") || key.includes("estimate"))
    return <IconClipboard className={cls} />;
  if (key.includes("open_recommendation") || key.includes("advisor"))
    return <IconSpark className={cls} />;
  if (key.includes("inactive") || key.includes("lapsed") || key.includes("win"))
    return <IconUserOff className={cls} />;
  if (
    key.includes("maintenance") ||
    key.includes("oil") ||
    key.includes("service") ||
    key.includes("reminder")
  )
    return <IconWrench className={cls} />;
  if (key.includes("missed") || key.includes("appointment"))
    return <IconCalendarMissed className={cls} />;
  if (key.includes("thank") || key.includes("review"))
    return <IconSpark className={cls} />;
  if (key.includes("recall") || key.includes("alert"))
    return <IconClipboard className={cls} />;
  return <IconSpark className={cls} />;
}

export default function MarketingPage() {
  const { session, loading: authLoading } = useAuth();
  const [suggestedActions, setSuggestedActions] = useState<SuggestedAction[]>([]);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [audience, setAudience] = useState<AudienceMember[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(
    null,
  );
  const [activeActionId, setActiveActionId] = useState<string | null>(null);
  const [aiPreview, setAiPreview] = useState<AiPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [portalReady, setPortalReady] = useState(false);
  const [copied, setCopied] = useState(false);
  const [audienceExpanded, setAudienceExpanded] = useState(false);
  const audienceListRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useEffect(() => {
    if (!audienceExpanded) return;
    const onPointerDown = (e: PointerEvent) => {
      const root = audienceListRef.current;
      if (!root) return;
      if (e.target instanceof Node && !root.contains(e.target)) {
        setAudienceExpanded(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [audienceExpanded]);

  const closeFollowupDialog = useCallback(() => {
    if (busy || previewBusy) return;
    setSelected(null);
    setAudience([]);
    setAudienceExpanded(false);
    setSelectedCustomerId(null);
    setActiveActionId(null);
    setAiPreview(null);
    setCopied(false);
  }, [busy, previewBusy]);

  const copyPreviewMessage = useCallback(async () => {
    const text = (
      aiPreview?.message ||
      selected?.ai_defaults?.message ||
      selected?.custom_message ||
      ""
    )
      .replace(/\n{2,}/g, "\n")
      .trim();
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Could not copy message");
    }
  }, [aiPreview, selected]);

  const refresh = useCallback(async () => {
    const actionsResult = await listSuggestedActions().catch(
      () => [] as SuggestedAction[],
    );
    setSuggestedActions(
      actionsResult.filter((action) => action.id !== "missed_appointment"),
    );
  }, []);

  useEffect(() => {
    if (authLoading || !session) return;
    void (async () => {
      setLoadingList(true);
      try {
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Load failed");
      } finally {
        setLoadingList(false);
      }
    })();
  }, [authLoading, session, refresh]);

  const previewMessageRaw =
    aiPreview?.message ||
    selected?.ai_defaults?.message ||
    selected?.custom_message ||
    null;
  const previewMessage = previewMessageRaw
    ? previewMessageRaw.replace(/\n{2,}/g, "\n").trim()
    : null;

  const flowStep = !selected ? 0 : !previewMessage ? 1 : 2;

  async function loadPreview(
    campaign: Campaign,
    customerId?: string | null,
    prefetched?: AiPreview | null,
  ) {
    const preview =
      prefetched ??
      ((await getAiPreview(
        campaign.id,
        customerId ?? undefined,
      )) as AiPreview);
    setAiPreview(preview);
    if (preview.customer_id) {
      setSelectedCustomerId(preview.customer_id);
    } else if (customerId) {
      setSelectedCustomerId(customerId);
    }
    return preview;
  }

  async function onSelectCustomer(member: AudienceMember) {
    if (!selected || previewBusy || member.customer_id === selectedCustomerId) {
      return;
    }
    setPreviewBusy(true);
    setError(null);
    setCopied(false);
    try {
      await loadPreview(selected, member.customer_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load preview");
    } finally {
      setPreviewBusy(false);
    }
  }

  async function onSelectAction(action: SuggestedAction) {
    if (action.count <= 0) {
      setError("No matching customers for this follow-up yet");
      return;
    }
    setBusy(true);
    setError(null);
    setAiPreview(null);
    setAudience([]);
    setAudienceExpanded(false);
    setSelectedCustomerId(null);
    try {
      const created = await createCampaign({
        name: `${action.title} follow-up`,
        campaign_type: action.campaign_type,
        channels_allowed: [...PREVIEW_CHANNELS],
        use_demo_audience: false,
        auto_schedule: false,
        expected_revenue: "500",
        tags: ["ai-followup", action.id],
        ...(action.custom_message ? { custom_message: action.custom_message } : {}),
      });
      const {
        ai_preview: prefetched,
        audience: createdAudience,
        ...campaign
      } = created;
      const members = createdAudience ?? [];
      setSelected(campaign);
      setAudience(members);
      setActiveActionId(action.id);
      const initialId =
        prefetched?.customer_id ?? members[0]?.customer_id ?? null;
      setSelectedCustomerId(initialId);
      await loadPreview(campaign, initialId, prefetched ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start follow-up");
    } finally {
      setBusy(false);
    }
  }

  const confidencePct =
    (aiPreview?.confidence ?? selected?.ai_defaults?.confidence) != null
      ? Math.round(
          (aiPreview?.confidence ?? selected?.ai_defaults?.confidence ?? 0) * 100,
        )
      : null;

  const reasons = (
    aiPreview?.reasons ??
    selected?.ai_defaults?.reasons ??
    []
  ).filter(
    (r) =>
      !r.startsWith("channel=") &&
      !r.startsWith("send_window=") &&
      !r.startsWith("frequency="),
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-hidden md:h-full">
      <header className="relative shrink-0 overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,var(--accent-soft),transparent_55%),linear-gradient(135deg,#fff_0%,#fafafa_100%)]"
          aria-hidden
        />
        <div
          className="pointer-events-none absolute -right-10 -top-16 h-48 w-48 rounded-full bg-[var(--accent-glow)] blur-3xl"
          aria-hidden
        />
        <div className="relative px-5 py-5 sm:px-6 sm:py-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <IconMarketing className="h-5 w-5 shrink-0 text-[var(--muted)]" />
              <h1 className="page-title">Marketing</h1>
            </div>
            <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-[var(--muted)]">
              AI suggests who to contact and drafts the message — preview only
            </p>
          </div>
        </div>
      </header>

      {error && (
        <p className="shrink-0 rounded-xl border border-red-200/80 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="mx-auto flex min-h-0 w-full max-w-2xl flex-1 flex-col gap-6 overflow-hidden">
        <nav aria-label="Follow-up steps" className="w-full shrink-0">
          <ol className="grid w-full grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto_minmax(0,1fr)] items-start">
            {STEPS.map((label, i) => {
              const done = i < flowStep;
              const current = i === flowStep;
              return (
                <li key={label} className="contents">
                  <div className="flex min-w-0 flex-col items-center gap-1.5 px-0.5 text-center">
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-colors ${
                        done || current
                          ? "bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]"
                          : "bg-white text-[var(--muted)] ring-1 ring-[var(--line)]"
                      }`}
                    >
                      {done ? "✓" : i + 1}
                    </span>
                    <span
                      className={`w-full break-words text-balance text-[10px] font-medium uppercase leading-snug tracking-[0.04em] sm:text-[11px] sm:tracking-[0.06em] ${
                        done || current
                          ? "text-[var(--foreground)]"
                          : "text-[var(--muted)]"
                      }`}
                    >
                      {label}
                    </span>
                  </div>
                  {i < STEPS.length - 1 && (
                    <div
                      className={`mt-4 h-px w-2.5 shrink-0 sm:w-8 ${
                        i < flowStep
                          ? "bg-[var(--accent)]"
                          : "bg-[var(--line)]"
                      }`}
                      aria-hidden
                    />
                  )}
                </li>
              );
            })}
          </ol>
        </nav>

        <section className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
          <div className="shrink-0">
            <p className="text-xs text-[var(--muted)]">
              Pick a suggested action — browse every matching customer and draft
            </p>
          </div>

          <div className="asa-scroll min-h-0 flex-1 space-y-2.5 overflow-y-auto overscroll-contain pb-6 [scrollbar-gutter:stable]">
            {loadingList &&
              Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="h-[4.75rem] animate-pulse rounded-2xl border border-[var(--line)] bg-[var(--panel)]"
                  style={{ animationDelay: `${i * 80}ms` }}
                />
              ))}

            {!loadingList && suggestedActions.length === 0 && (
              <div className="rounded-2xl border border-dashed border-[var(--line)] bg-[var(--panel)] px-6 py-10 text-center">
                <span className="mx-auto inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/15">
                  <IconSpark className="h-5 w-5" />
                </span>
                <p className="mt-3 text-sm font-medium">No recommendations yet</p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  AI will surface follow-ups when matching customers appear
                </p>
              </div>
            )}

            {suggestedActions.map((action, index) => {
              const active = activeActionId === action.id;
              const empty = action.count <= 0;
              return (
                <button
                  key={action.id}
                  type="button"
                  disabled={busy || empty}
                  onClick={() => void onSelectAction(action)}
                  style={{ animationDelay: `${index * 45}ms` }}
                  className={`group relative w-full overflow-hidden rounded-2xl border px-4 py-4 text-left transition-all duration-200 [animation:rise-in_0.45s_ease_both] disabled:cursor-not-allowed disabled:opacity-55 ${
                    active
                      ? "border-[var(--accent)]/50 bg-[var(--accent-soft)] shadow-[0_12px_36px_-20px_var(--accent-glow)] ring-1 ring-[var(--accent)]/25"
                      : "border-[var(--line)] bg-[var(--panel)] shadow-[0_1px_0_rgba(255,255,255,0.9)_inset] hover:-translate-y-0.5 hover:border-[var(--accent)]/35 hover:shadow-[0_18px_40px_-28px_rgba(0,0,0,0.35)]"
                  }`}
                >
                  <div
                    className={`pointer-events-none absolute inset-y-0 left-0 w-1 transition-colors ${
                      active ? "bg-[var(--accent)]" : "bg-transparent group-hover:bg-[var(--accent)]/40"
                    }`}
                    aria-hidden
                  />
                  <div className="flex items-start gap-3.5">
                    <span
                      className={`mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors ${
                        active
                          ? "bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]"
                          : "bg-[linear-gradient(145deg,var(--accent-soft),#fff)] text-[var(--accent)] ring-1 ring-[var(--accent)]/15"
                      }`}
                    >
                      {actionIcon(action)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <p className="text-sm font-semibold tracking-tight text-[var(--foreground)]">
                          {action.title}
                        </p>
                        <span
                          className={`shrink-0 rounded-lg px-2 py-0.5 text-[11px] font-medium tabular-nums ${
                            empty
                              ? "bg-[var(--background)] text-[var(--muted)]"
                              : "bg-white text-[var(--accent)] ring-1 ring-[var(--accent)]/20"
                          }`}
                        >
                          {action.hint}
                        </span>
                      </div>
                      <p className="mt-1 text-xs leading-relaxed text-[var(--muted)]">
                        {action.description}
                      </p>
                      <div className="mt-2.5 flex items-center justify-between gap-2">
                        <span className="text-[11px] text-[var(--muted)]">
                          {empty
                            ? "No matching customers"
                            : busy && active
                              ? "Preparing preview…"
                              : "Tap to draft preview"}
                        </span>
                        {!empty && (
                          <span
                            className={`inline-flex items-center gap-1 text-[11px] font-medium transition-colors ${
                              active
                                ? "text-[var(--accent)]"
                                : "text-[var(--muted)] group-hover:text-[var(--accent)]"
                            }`}
                          >
                            Open
                            <IconArrow className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </section>
      </div>

      {portalReady &&
        selected &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px] [animation:rise-in_0.2s_ease_both]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="followup-dialog-title"
            onClick={(e) => {
              if (e.target === e.currentTarget) closeFollowupDialog();
            }}
          >
            <section
              className="flex max-h-[min(88vh,680px)] w-full max-w-md flex-col overflow-hidden rounded-[1.2rem] border border-[var(--line)] bg-[var(--panel)] shadow-[0_28px_80px_-36px_rgba(0,0,0,0.5)] [animation:reveal-scale_0.28s_ease_both]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="relative shrink-0 overflow-hidden rounded-t-[1.2rem] border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-4 pb-4 pt-4">
                <div
                  className="pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-[var(--accent-glow)] blur-2xl"
                  aria-hidden
                />
                <div className="relative flex items-start gap-2.5">
                  <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]">
                    <IconUser className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <h2
                      id="followup-dialog-title"
                      className="text-base font-semibold tracking-tight"
                      style={{ fontFamily: "var(--font-display)" }}
                    >
                      Review customers
                    </h2>
                    <p className="mt-0.5 text-xs text-[var(--muted)]">
                      {selected.name}
                      {audience.length > 0
                        ? ` · ${audience.length} customer${audience.length === 1 ? "" : "s"}`
                        : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label="Close"
                    disabled={busy || previewBusy}
                    onClick={() => closeFollowupDialog()}
                    className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-[var(--muted)] transition hover:bg-black/[0.05] hover:text-[var(--foreground)] disabled:opacity-50"
                  >
                    <IconX className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4 pb-5">
                <div>
                  <div className="mb-2.5 flex items-center justify-between gap-2">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                      Matching customers
                    </p>
                    <span className="text-[11px] tabular-nums text-[var(--muted)]">
                      {audience.length}
                    </span>
                  </div>
                  {audience.length === 0 ? (
                    <div className="rounded-2xl border border-dashed border-[var(--line)] bg-[var(--background)]/50 px-4 py-6 text-center text-sm text-[var(--muted)]">
                      No customers in this follow-up
                    </div>
                  ) : (
                    <div ref={audienceListRef} className="space-y-2">
                      {audience.length > 1 ? (
                        <button
                          type="button"
                          onClick={() =>
                            setAudienceExpanded((open) => !open)
                          }
                          className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2 text-xs font-semibold text-[var(--muted)] transition hover:bg-black/[0.03] hover:text-[var(--foreground)]"
                        >
                          {audienceExpanded
                            ? "Show less"
                            : `Show all ${audience.length} customers`}
                        </button>
                      ) : null}
                      <div className="relative">
                        {(() => {
                          const renderMember = (member: AudienceMember) => {
                            const active =
                              member.customer_id === selectedCustomerId;
                            const contact =
                              member.email?.trim() ||
                              member.phone?.trim() ||
                              "—";
                            const meta = [member.vehicle, member.service]
                              .filter(Boolean)
                              .join(" · ");
                            return (
                              <li key={member.customer_id}>
                                <button
                                  type="button"
                                  disabled={previewBusy}
                                  onClick={() => {
                                    void onSelectCustomer(member);
                                    if (audienceExpanded) {
                                      setAudienceExpanded(false);
                                    }
                                  }}
                                  className={`flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition disabled:cursor-wait ${
                                    active
                                      ? "bg-[var(--accent-soft)] ring-1 ring-[var(--accent)]/30"
                                      : "hover:bg-black/[0.03]"
                                  }`}
                                >
                                  <span
                                    className={`mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-xs font-semibold ${
                                      active
                                        ? "bg-[var(--accent)] text-white"
                                        : "bg-white text-[var(--muted)] ring-1 ring-[var(--line)]"
                                    }`}
                                  >
                                    {(member.name || "?")
                                      .slice(0, 1)
                                      .toUpperCase()}
                                  </span>
                                  <span className="min-w-0 flex-1">
                                    <span className="block truncate text-sm font-semibold tracking-tight">
                                      {member.name || "Customer"}
                                    </span>
                                    <span className="mt-0.5 block truncate text-xs text-[var(--muted)]">
                                      {contact}
                                    </span>
                                    {meta ? (
                                      <span className="mt-0.5 block truncate text-[11px] text-[var(--muted)]">
                                        {meta}
                                      </span>
                                    ) : null}
                                  </span>
                                  {active && (
                                    <span className="mt-1 shrink-0 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--accent)]">
                                      Selected
                                    </span>
                                  )}
                                </button>
                              </li>
                            );
                          };
                          const selectedMember =
                            audience.find(
                              (m) => m.customer_id === selectedCustomerId,
                            ) ?? audience[0];
                          return (
                            <>
                              <ul className="space-y-1.5 rounded-2xl border border-[var(--line)] bg-[linear-gradient(180deg,#fff_0%,#fafafa_100%)] p-1.5">
                                {selectedMember
                                  ? renderMember(selectedMember)
                                  : null}
                              </ul>
                              {audienceExpanded ? (
                                <ul className="absolute left-0 right-0 top-0 z-20 max-h-[min(40vh,280px)] space-y-1.5 overflow-y-auto overscroll-contain rounded-2xl border border-[var(--line)] bg-[linear-gradient(180deg,#fff_0%,#fafafa_100%)] p-1.5 shadow-[0_18px_40px_-20px_rgba(0,0,0,0.45)]">
                                  {audience.map(renderMember)}
                                </ul>
                              ) : null}
                            </>
                          );
                        })()}
                      </div>
                    </div>
                  )}
                </div>

                <div className="rounded-2xl border border-[var(--line)] bg-[linear-gradient(180deg,#fff_0%,#fafafa_100%)] p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                        Selected customer
                      </p>
                      <p className="mt-1 truncate text-base font-semibold tracking-tight">
                        {aiPreview?.customer_name
                          ? aiPreview.customer_name
                          : busy || previewBusy
                            ? "Loading…"
                            : "—"}
                      </p>
                      <p className="mt-1 text-sm text-[var(--muted)]">
                        {aiPreview?.email?.trim() ||
                          aiPreview?.phone?.trim() ||
                          "—"}
                      </p>
                      {(aiPreview?.vehicle || aiPreview?.service) && (
                        <p className="mt-2 text-xs text-[var(--muted)]">
                          {[aiPreview.vehicle, aiPreview.service]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      )}
                    </div>
                    {confidencePct != null && (
                      <div className="shrink-0 text-right">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                          Confidence
                        </p>
                        <p className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-[var(--accent)]">
                          {confidencePct}
                          <span className="text-sm font-medium">%</span>
                        </p>
                        <div className="mt-1.5 h-1 w-16 overflow-hidden rounded-full bg-[var(--accent-soft)]">
                          <div
                            className="h-full rounded-full bg-[var(--accent)] transition-all"
                            style={{ width: `${Math.min(100, confidencePct)}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                  {reasons.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5 border-t border-[var(--line)] pt-3">
                      {reasons.map((reason) => (
                        <span
                          key={reason}
                          className="rounded-lg bg-white px-2 py-1 text-[11px] text-[var(--muted)] ring-1 ring-[var(--line)]"
                        >
                          {reason}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                <div>
                  <div className="mb-2.5 flex items-center gap-2">
                    <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">
                      <IconMail className="h-3.5 w-3.5" />
                    </span>
                    <h3 className="text-sm font-semibold tracking-tight">
                      AI Message
                    </h3>
                    <button
                      type="button"
                      disabled={busy || previewBusy || !previewMessage}
                      onClick={() => void copyPreviewMessage()}
                      className="ml-auto inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-[var(--muted)] transition hover:bg-black/[0.04] hover:text-[var(--foreground)] disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      {copied ? (
                        <>
                          <IconCheck className="h-3.5 w-3.5 text-[var(--accent)]" />
                          Copied
                        </>
                      ) : (
                        <>
                          <IconCopy className="h-3.5 w-3.5" />
                          Copy
                        </>
                      )}
                    </button>
                  </div>
                  <div className="flex max-h-[min(36vh,260px)] flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-[inset_0_1px_0_rgba(255,255,255,0.9)]">
                    <div className="flex shrink-0 items-center gap-1.5 border-b border-[var(--line)] bg-[var(--background)]/60 px-3 py-2">
                      <span className="h-2 w-2 rounded-full bg-[#ff5f57]" />
                      <span className="h-2 w-2 rounded-full bg-[#febc2e]" />
                      <span className="h-2 w-2 rounded-full bg-[#28c840]" />
                      <span className="ml-2 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
                        Preview
                      </span>
                    </div>
                    <div className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain whitespace-pre-wrap px-4 py-4 text-sm leading-relaxed text-[var(--foreground)]">
                      {(busy || previewBusy) && !previewMessage
                        ? "Generating…"
                        : previewBusy
                          ? "Updating…"
                          : (previewMessage ?? "No AI draft yet")}
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>,
          document.body,
        )}
    </div>
  );
}
