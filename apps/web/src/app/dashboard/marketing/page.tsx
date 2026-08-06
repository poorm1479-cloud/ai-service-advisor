"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  AnalyticsSummary,
  CalendarEvent,
  Campaign,
  CampaignMessage,
  CampaignMetrics,
  SuggestedAction,
  createCampaign,
  getAiPreview,
  getAnalyticsSummary,
  getCampaignAnalytics,
  getCampaignCalendar,
  listCampaignMessages,
  listCampaigns,
  listChannels,
  listSuggestedActions,
  processCampaign,
  processQueue,
  scheduleCampaign,
  trackMessage,
  updateCampaign,
} from "@/lib/marketing";

type Tab = "followup" | "messages" | "calendar" | "analytics";

type AiPreview = {
  customer_id?: string;
  customer_name?: string;
  phone?: string | null;
  email?: string | null;
  vehicle?: string | null;
  service?: string | null;
  channel?: string;
  send_at?: string;
  message?: string;
  subject?: string | null;
  frequency_days?: number;
  confidence?: number;
  reasons?: string[];
};

const STEPS = ["AI Recommendations", "Review customer", "AI message", "Send"] as const;

export default function MarketingPage() {
  const { session, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<Tab>("followup");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [channels, setChannels] = useState<string[]>([]);
  const [suggestedActions, setSuggestedActions] = useState<SuggestedAction[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<CampaignMetrics | null>(null);
  const [messages, setMessages] = useState<CampaignMessage[]>([]);
  const [aiPreview, setAiPreview] = useState<AiPreview | null>(null);
  const [channelOverride, setChannelOverride] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sentFlash, setSentFlash] = useState(false);

  const refresh = useCallback(async () => {
    const [c, cal, sum, actionsResult] = await Promise.all([
      listCampaigns(),
      getCampaignCalendar(),
      getAnalyticsSummary(),
      listSuggestedActions().catch(() => [] as SuggestedAction[]),
    ]);
    setCampaigns(c);
    setEvents(cal);
    setSummary(sum);
    setSuggestedActions(actionsResult);
    return c;
  }, []);

  const canEditCampaign = (c: Campaign | null) =>
    !!c && (c.status === "draft" || c.status === "paused" || c.status === "scheduled");

  useEffect(() => {
    if (authLoading || !session) return;
    void (async () => {
      try {
        setChannels(await listChannels());
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Load failed");
      }
    })();
  }, [authLoading, session, refresh]);

  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const e of events) {
      const list = map.get(e.day) ?? [];
      list.push(e);
      map.set(e.day, list);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [events]);

  const recommendedChannel =
    channelOverride ?? aiPreview?.channel ?? selected?.ai_defaults?.channel ?? "sms";

  const previewMessage =
    aiPreview?.message ?? selected?.ai_defaults?.message ?? null;

  const flowStep = !selected ? 0 : !previewMessage ? 1 : sentFlash ? 3 : 2;

  async function loadPreview(campaign: Campaign, channel?: string) {
    const preview = (await getAiPreview(campaign.id)) as AiPreview;
    setAiPreview(preview);
    if (!channel) {
      setChannelOverride(null);
    }
    return preview;
  }

  async function onSelectAction(action: SuggestedAction) {
    if (action.count <= 0) {
      setError("No matching customers for this follow-up yet");
      return;
    }
    setBusy(true);
    setError(null);
    setSentFlash(false);
    setTab("followup");
    try {
      const allowed =
        channels.length > 0 ? channels : ["sms", "email", "voice"];
      const created = await createCampaign({
        name: `${action.title} follow-up`,
        campaign_type: action.campaign_type,
        channels_allowed: allowed,
        use_demo_audience: false,
        auto_schedule: false,
        expected_revenue: "500",
        tags: ["ai-followup", action.id],
        ...(action.custom_message ? { custom_message: action.custom_message } : {}),
      });
      setSelected(created);
      setActiveActionId(action.id);
      await loadPreview(created);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start follow-up");
    } finally {
      setBusy(false);
    }
  }

  async function onSelectExisting(campaign: Campaign) {
    setBusy(true);
    setError(null);
    setSentFlash(false);
    setTab("followup");
    try {
      setSelected(campaign);
      setActiveActionId(
        campaign.tags.find((t) => suggestedActions.some((a) => a.id === t)) ?? null,
      );
      await loadPreview(campaign);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load follow-up");
    } finally {
      setBusy(false);
    }
  }

  async function onChannelOverride(ch: string) {
    if (!selected || !canEditCampaign(selected)) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateCampaign(selected.id, {
        channels_allowed: [ch],
      });
      setSelected(updated);
      setChannelOverride(ch);
      await loadPreview(updated, ch);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Channel update failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSend() {
    if (!selected || !canEditCampaign(selected)) return;
    setBusy(true);
    setError(null);
    try {
      if (channelOverride) {
        const updated = await updateCampaign(selected.id, {
          channels_allowed: [channelOverride],
        });
        setSelected(updated);
      }
      await scheduleCampaign(selected.id);
      await processCampaign(selected.id);
      setSentFlash(true);
      const list = await refresh();
      const latest = list.find((x) => x.id === selected.id);
      if (latest) setSelected(latest);
      setMessages(await listCampaignMessages(selected.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  async function onLoadMessages() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      setMessages(await listCampaignMessages(selected.id));
      setTab("messages");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load messages failed");
    } finally {
      setBusy(false);
    }
  }

  async function onProcessQueue() {
    setBusy(true);
    setError(null);
    try {
      await processQueue();
      await refresh();
      if (selected) setMessages(await listCampaignMessages(selected.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Process queue failed");
    } finally {
      setBusy(false);
    }
  }

  const activeAction = suggestedActions.find((a) => a.id === activeActionId) ?? null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">AI Customer Follow-up</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            SMS · Email · Voice — AI suggests who to contact and drafts the message
          </p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onProcessQueue()}
          className="rounded-md bg-[var(--accent)] px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          Process queue
        </button>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setTab("followup")}
          className={`rounded-md px-3 py-1.5 text-sm ${
            tab === "followup"
              ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
              : "text-[var(--muted)] hover:bg-[var(--accent-soft)]"
          }`}
        >
          Follow-up
        </button>
        <button
          type="button"
          onClick={() => {
            setTab("messages");
            if (selected) void onLoadMessages();
          }}
          className={`rounded-md px-3 py-1.5 text-sm ${
            tab === "messages"
              ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
              : "text-[var(--muted)] hover:bg-[var(--accent-soft)]"
          }`}
        >
          Messages
        </button>
        <button
          type="button"
          onClick={() => setAdvancedOpen((v) => !v)}
          className="rounded-md px-3 py-1.5 text-sm text-[var(--muted)] hover:bg-[var(--accent-soft)]"
        >
          Advanced {advancedOpen ? "▾" : "▸"}
        </button>
        {advancedOpen && (
          <>
            <button
              type="button"
              onClick={() => setTab("calendar")}
              className={`rounded-md px-3 py-1.5 text-sm ${
                tab === "calendar"
                  ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                  : "text-[var(--muted)] hover:bg-[var(--accent-soft)]"
              }`}
            >
              Campaign Calendar
            </button>
            <button
              type="button"
              onClick={() => setTab("analytics")}
              className={`rounded-md px-3 py-1.5 text-sm ${
                tab === "analytics"
                  ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                  : "text-[var(--muted)] hover:bg-[var(--accent-soft)]"
              }`}
            >
              Campaign Analytics
            </button>
          </>
        )}
      </div>

      {error && (
        <p className="shrink-0 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <div className="asa-scroll min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain">
      {tab === "followup" && (
        <div className="space-y-6">
          <ol className="flex flex-wrap gap-2 text-xs">
            {STEPS.map((label, i) => (
              <li
                key={label}
                className={`rounded-md px-2.5 py-1 ${
                  i <= flowStep
                    ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
                    : "text-[var(--muted)]"
                }`}
              >
                {i + 1}. {label}
              </li>
            ))}
          </ol>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="space-y-3">
              <div>
                <h2 className="text-sm font-medium">AI Recommendations</h2>
                <p className="mt-0.5 text-xs text-[var(--muted)]">
                  Pick a suggested action — AI prepares the customer list and message
                </p>
              </div>
              <div className="space-y-2">
                {suggestedActions.map((action) => {
                  const active = activeActionId === action.id;
                  const empty = action.count <= 0;
                  return (
                    <button
                      key={action.id}
                      type="button"
                      disabled={busy || empty}
                      onClick={() => void onSelectAction(action)}
                      className={`w-full rounded-md border px-4 py-3 text-left transition-colors disabled:opacity-60 ${
                        active
                          ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                          : "border-[var(--line)] bg-[var(--panel)] hover:border-[var(--accent)]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium">{action.title}</p>
                        <span className="shrink-0 text-[11px] text-[var(--muted)]">
                          {action.hint}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-[var(--muted)]">{action.description}</p>
                    </button>
                  );
                })}
              </div>

              {campaigns.length > 0 && (
                <div className="pt-2">
                  <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                    Recent follow-ups
                  </h3>
                  <ul className="mt-2 space-y-1">
                    {campaigns.slice(0, 6).map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void onSelectExisting(c)}
                          className={`w-full rounded-md px-3 py-2 text-left text-sm disabled:opacity-60 ${
                            selected?.id === c.id
                              ? "bg-[var(--accent-soft)] text-[var(--accent)]"
                              : "hover:bg-[var(--accent-soft)]"
                          }`}
                        >
                          <span className="font-medium">{c.name}</span>
                          <span className="ml-2 text-xs text-[var(--muted)]">
                            {c.status} · {c.audience_count} customers
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </section>

            <section className="space-y-4 rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
              {!selected ? (
                <div className="flex min-h-[280px] flex-col items-center justify-center text-center">
                  <p className="text-sm font-medium">Select a recommendation</p>
                  <p className="mt-1 max-w-xs text-xs text-[var(--muted)]">
                    AI will pull the matching customers, recommend a channel, and draft the message.
                  </p>
                </div>
              ) : (
                <>
                  <div>
                    <h2 className="text-sm font-medium">Review customer</h2>
                    <p className="mt-0.5 text-xs text-[var(--muted)]">
                      {activeAction?.title ?? selected.campaign_type.replaceAll("_", " ")} ·{" "}
                      {selected.audience_count} in audience
                    </p>
                    <div className="mt-3 space-y-2 text-sm">
                      <p>
                        <span className="text-[var(--muted)]">Customer:</span>{" "}
                        {aiPreview?.customer_name
                          ? aiPreview.customer_name
                          : busy
                            ? "Loading…"
                            : "—"}
                      </p>
                      {(aiPreview?.phone || aiPreview?.email) && (
                        <p>
                          <span className="text-[var(--muted)]">Contact:</span>{" "}
                          {aiPreview.phone || aiPreview.email}
                        </p>
                      )}
                      {(aiPreview?.vehicle || aiPreview?.service) && (
                        <p>
                          <span className="text-[var(--muted)]">Context:</span>{" "}
                          {[aiPreview.vehicle, aiPreview.service].filter(Boolean).join(" · ")}
                        </p>
                      )}
                      <p>
                        <span className="text-[var(--muted)]">Best send time:</span>{" "}
                        {aiPreview?.send_at
                          ? new Date(aiPreview.send_at).toLocaleString()
                          : selected.ai_defaults?.send_at
                            ? new Date(selected.ai_defaults.send_at).toLocaleString()
                            : "—"}
                      </p>
                      {(aiPreview?.confidence ?? selected.ai_defaults?.confidence) != null && (
                        <p>
                          <span className="text-[var(--muted)]">Confidence:</span>{" "}
                          {(
                            (aiPreview?.confidence ?? selected.ai_defaults?.confidence ?? 0) * 100
                          ).toFixed(0)}
                          %
                        </p>
                      )}
                      {(aiPreview?.reasons ?? selected.ai_defaults?.reasons)?.length ? (
                        <p className="text-xs text-[var(--muted)]">
                          {(aiPreview?.reasons ?? selected.ai_defaults?.reasons ?? []).join(" · ")}
                        </p>
                      ) : null}
                    </div>
                  </div>

                  <div className="border-t border-[var(--line)] pt-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h2 className="text-sm font-medium">AI Message Preview</h2>
                      {aiPreview?.subject && (
                        <span className="text-xs text-[var(--muted)]">
                          Subject: {aiPreview.subject}
                        </span>
                      )}
                    </div>

                    <div className="mt-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-xs text-[var(--muted)]">Channel</p>
                        <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--accent)]">
                          AI recommends {(aiPreview?.channel ?? selected.ai_defaults?.channel ?? "sms").toUpperCase()}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {(channels.length ? channels : ["sms", "email", "voice"]).map((ch) => {
                          const isAi =
                            ch === (aiPreview?.channel ?? selected.ai_defaults?.channel);
                          const isSelected = ch === recommendedChannel;
                          const editable = canEditCampaign(selected);
                          return (
                            <button
                              key={ch}
                              type="button"
                              disabled={busy || !editable}
                              onClick={() => void onChannelOverride(ch)}
                              className={`rounded-md px-3 py-1 text-xs uppercase disabled:opacity-60 ${
                                isSelected
                                  ? "bg-[var(--accent)] font-medium text-white"
                                  : "border border-[var(--line)] text-[var(--muted)] hover:border-[var(--accent)]"
                              }`}
                            >
                              {ch}
                              {isAi && !channelOverride ? " · AI" : ""}
                            </button>
                          );
                        })}
                      </div>
                      <p className="mt-1.5 text-[11px] text-[var(--muted)]">
                        {canEditCampaign(selected)
                          ? "Override SMS, Email, or Voice anytime — AI regenerates the message for that channel."
                          : "Channel is locked after send."}
                      </p>
                    </div>

                    <div className="mt-3 whitespace-pre-wrap rounded-md border border-[var(--line)] p-3 text-sm">
                      {previewMessage ?? (busy ? "Generating…" : "No preview yet")}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-4">
                    <button
                      type="button"
                      disabled={busy || !previewMessage || !canEditCampaign(selected)}
                      onClick={() => void onSend()}
                      className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                    >
                      {busy
                        ? "Working…"
                        : canEditCampaign(selected)
                          ? "Send"
                          : "Already sent"}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onLoadMessages()}
                      className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-60"
                    >
                      View messages
                    </button>
                    {sentFlash && (
                      <span className="text-xs font-medium text-[var(--accent)]">
                        Follow-up queued and processed
                      </span>
                    )}
                  </div>
                </>
              )}
            </section>
          </div>
        </div>
      )}

      {tab === "calendar" && (
        <div className="space-y-3">
          <p className="text-xs text-[var(--muted)]">Advanced · Campaign Calendar</p>
          {eventsByDay.length === 0 && (
            <p className="text-sm text-[var(--muted)]">No scheduled sends in range</p>
          )}
          {eventsByDay.map(([day, items]) => (
            <div key={day} className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-4">
              <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{day}</p>
              <ul className="mt-2 space-y-2">
                {items.map((e) => (
                  <li key={`${e.campaign_id}-${e.day}-${e.channel}`} className="text-sm">
                    <span className="font-medium">{e.name}</span>
                    <span className="text-[var(--muted)]">
                      {" "}
                      · {e.campaign_type.replaceAll("_", " ")} · {e.channel ?? "multi"} ·{" "}
                      {e.message_count} msgs · {e.status}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {tab === "analytics" && summary && (
        <div className="space-y-6">
          <p className="text-xs text-[var(--muted)]">Advanced · Campaign Analytics</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Follow-ups" value={String(summary.campaigns)} />
            <Metric label="Sent" value={String(summary.sent)} />
            <Metric label="Open rate" value={`${(summary.open_rate * 100).toFixed(1)}%`} />
            <Metric label="ROI" value={`${summary.roi.toFixed(1)}x`} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Click rate" value={`${(summary.click_rate * 100).toFixed(1)}%`} />
            <Metric label="Reply rate" value={`${(summary.reply_rate * 100).toFixed(1)}%`} />
            <Metric
              label="Appointment rate"
              value={`${(summary.appointment_rate * 100).toFixed(1)}%`}
            />
            <Metric label="Revenue" value={`$${Number(summary.revenue).toLocaleString()}`} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
              <h2 className="text-sm font-medium">By channel</h2>
              <div className="mt-3 space-y-2">
                {Object.entries(summary.by_channel).map(([ch, n]) => {
                  const max = Math.max(...Object.values(summary.by_channel), 1);
                  return (
                    <div key={ch}>
                      <div className="flex justify-between text-xs text-[var(--muted)]">
                        <span className="uppercase">{ch}</span>
                        <span>{n}</span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-[var(--line)]">
                        <div
                          className="h-full bg-[var(--accent)]"
                          style={{ width: `${(n / max) * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
            <section className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
              <h2 className="text-sm font-medium">Follow-up performance</h2>
              <div className="mt-3 space-y-2 text-sm">
                {summary.campaigns_detail.map((c) => (
                  <button
                    key={c.campaign_id}
                    type="button"
                    className="block w-full rounded-md border border-[var(--line)] px-3 py-2 text-left hover:border-[var(--accent)]"
                    onClick={() =>
                      void getCampaignAnalytics(c.campaign_id)
                        .then(setMetrics)
                        .catch((err) => setError(String(err)))
                    }
                  >
                    <p className="font-medium">{c.name}</p>
                    <p className="text-xs text-[var(--muted)]">
                      open {(c.open_rate * 100).toFixed(0)}% · reply {(c.reply_rate * 100).toFixed(0)}% ·
                      ROI {c.roi.toFixed(1)}x · ${Number(c.revenue).toLocaleString()}
                    </p>
                  </button>
                ))}
              </div>
            </section>
          </div>

          {metrics && (
            <section className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-5 text-sm">
              <h2 className="text-sm font-medium">Selected follow-up metrics</h2>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <p>Sent: {metrics.sent}</p>
                <p>Opened: {metrics.opened}</p>
                <p>Clicked: {metrics.clicked}</p>
                <p>Replied: {metrics.replied}</p>
                <p>Appointments: {metrics.appointments}</p>
                <p>Revenue: ${Number(metrics.revenue).toLocaleString()}</p>
              </div>
            </section>
          )}
        </div>
      )}

      {tab === "messages" && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-medium">
              Messages {selected ? `· ${selected.name}` : ""}
            </h2>
            <button
              type="button"
              disabled={busy || !selected}
              onClick={() => void onLoadMessages()}
              className="rounded-md border border-[var(--line)] px-3 py-1.5 text-xs disabled:opacity-60"
            >
              Refresh
            </button>
          </div>
          {!selected && (
            <p className="text-sm text-[var(--muted)]">
              Start a follow-up from the Follow-up tab to see messages
            </p>
          )}
          <div className="space-y-2">
            {messages.map((m) => (
              <div
                key={m.id}
                className="flex flex-wrap items-start justify-between gap-2 rounded-md border border-[var(--line)] bg-[var(--panel)] px-3 py-2 text-sm"
              >
                <div className="min-w-0">
                  <p className="font-medium">
                    {m.channel} · {m.status}
                  </p>
                  <p className="mt-1 text-xs text-[var(--muted)] line-clamp-2">{m.body}</p>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-60"
                  onClick={() =>
                    void trackMessage(m.id, "opened")
                      .then(async () => {
                        if (selected) setMessages(await listCampaignMessages(selected.id));
                      })
                      .catch((err) => setError(String(err)))
                  }
                >
                  Track opened
                </button>
              </div>
            ))}
            {selected && messages.length === 0 && (
              <p className="text-sm text-[var(--muted)]">No messages for this follow-up yet</p>
            )}
          </div>
        </section>
      )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-xl font-semibold tracking-tight">{value}</p>
    </div>
  );
}
