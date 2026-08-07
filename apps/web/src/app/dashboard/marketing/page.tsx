"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/lib/auth";
import {
  AnalyticsSummary,
  Campaign,
  CampaignMessage,
  SuggestedAction,
  createCampaign,
  deleteCampaignMessages,
  getAiPreview,
  getAnalyticsSummary,
  listCampaignMessages,
  listCampaigns,
  listChannels,
  listSuggestedActions,
  processCampaign,
  scheduleCampaign,
  updateCampaign,
  type AiPreview,
} from "@/lib/marketing";

type Tab = "followup" | "messages" | "analytics";

const STEPS = ["AI Recommendations", "Review customer", "AI message", "Send"] as const;
/** Review customer: SMS / Email only (no voice). */
const REVIEW_CHANNELS = ["sms", "email"] as const;

export default function MarketingPage() {
  const { session, loading: authLoading } = useAuth();
  const [tab, setTab] = useState<Tab>("followup");
  const [channels, setChannels] = useState<string[]>([]);
  const [suggestedActions, setSuggestedActions] = useState<SuggestedAction[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [selected, setSelected] = useState<Campaign | null>(null);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<CampaignMessage[]>([]);
  /** Messages loaded for the Messages tab, tagged with parent campaign for type grouping. */
  const [tabMessages, setTabMessages] = useState<
    (CampaignMessage & { campaign_name: string; campaign_type: string })[]
  >([]);
  const [messagesTypeFilter, setMessagesTypeFilter] = useState<string | null>(null);
  const [selectedMessage, setSelectedMessage] = useState<
    (CampaignMessage & { campaign_name?: string; campaign_type?: string }) | null
  >(null);
  const [aiPreview, setAiPreview] = useState<AiPreview | null>(null);
  const [channelOverride, setChannelOverride] = useState<string | null>(null);
  const [messageDraft, setMessageDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sentFlash, setSentFlash] = useState(false);
  const [portalReady, setPortalReady] = useState(false);
  const [selectedMessageIds, setSelectedMessageIds] = useState<Set<string>>(new Set());
  const [deleteSelectedConfirm, setDeleteSelectedConfirm] = useState(false);
  /** Campaign IDs that still have at least one message (exclude fully deleted). */
  const [idsWithMessages, setIdsWithMessages] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setPortalReady(true);
  }, []);

  const closeFollowupDialog = useCallback(() => {
    if (busy) return;
    setSelected(null);
    setActiveActionId(null);
    setAiPreview(null);
    setChannelOverride(null);
    setMessageDraft("");
    setSentFlash(false);
    setMessages([]);
  }, [busy]);

  const refresh = useCallback(async (opts?: { light?: boolean }) => {
    // light: campaign list only — used after opening Review customer so the dialog
    // is not blocked by analytics / suggested-actions / N message probes.
    if (opts?.light) {
      const c = await listCampaigns();
      setCampaigns(c);
      return c;
    }

    const [c, sum, actionsResult] = await Promise.all([
      listCampaigns(),
      getAnalyticsSummary(),
      listSuggestedActions().catch(() => [] as SuggestedAction[]),
    ]);
    setCampaigns(c);
    setSummary(sum);
    setSuggestedActions(actionsResult);

    // Only list campaigns that still have message records (deleted ones drop out of Recent).
    const candidates = c.filter(
      (camp) => camp.status !== "draft" && camp.status !== "cancelled",
    );
    const present = await Promise.all(
      candidates.map(async (camp) => {
        try {
          const msgs = await listCampaignMessages(camp.id);
          return msgs.length > 0 ? camp.id : null;
        } catch {
          return null;
        }
      }),
    );
    setIdsWithMessages(new Set(present.filter((id): id is string => id != null)));

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

  /** Sent follow-ups that still have messages (not draft/cancelled and not fully deleted). */
  const recentSentFollowUps = useMemo(
    () =>
      campaigns
        .filter((c) => c.status !== "draft" && c.status !== "cancelled")
        .filter((c) => idsWithMessages.has(c.id))
        .slice(0, 6),
    [campaigns, idsWithMessages],
  );

  const typeLabel = useCallback((campaignType: string) => {
    const fromAction = suggestedActions.find((a) => a.campaign_type === campaignType);
    if (fromAction) return fromAction.title;
    return campaignType.replaceAll("_", " ");
  }, [suggestedActions]);

  /** Messages tab: group by campaign_type so the same kind appears in one place. */
  const messagesByType = useMemo(() => {
    const map = new Map<
      string,
      (CampaignMessage & { campaign_name: string; campaign_type: string })[]
    >();
    for (const m of tabMessages) {
      if (messagesTypeFilter && m.campaign_type !== messagesTypeFilter) continue;
      const list = map.get(m.campaign_type) ?? [];
      list.push(m);
      map.set(m.campaign_type, list);
    }
    return [...map.entries()]
      .map(([type, items]) => ({
        type,
        label: typeLabel(type),
        items: items.sort((a, b) => {
          const ta = a.sent_at ?? a.scheduled_at ?? "";
          const tb = b.sent_at ?? b.scheduled_at ?? "";
          return tb.localeCompare(ta);
        }),
      }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [tabMessages, messagesTypeFilter, typeLabel]);

  const messageTypeChips = useMemo(() => {
    const types = new Set(tabMessages.map((m) => m.campaign_type));
    return [...types]
      .map((type) => ({ type, label: typeLabel(type), count: tabMessages.filter((m) => m.campaign_type === type).length }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [tabMessages, typeLabel]);

  const aiChannel =
    channelOverride ?? aiPreview?.channel ?? selected?.ai_defaults?.channel ?? "sms";
  /** Voice is not offered in Review customer; map AI voice picks to SMS. */
  const recommendedChannel = aiChannel === "voice" ? "sms" : aiChannel;
  const reviewChannels = (channels.length ? channels : [...REVIEW_CHANNELS]).filter(
    (ch) => ch !== "voice",
  );

  /** Contact for the active channel only (email vs phone). */
  const reviewContact =
    recommendedChannel === "email"
      ? aiPreview?.email?.trim() || null
      : aiPreview?.phone?.trim() || null;
  const hasContact = Boolean(reviewContact);

  const previewMessage =
    messageDraft ||
    aiPreview?.message ||
    selected?.ai_defaults?.message ||
    null;

  const flowStep = !selected ? 0 : !previewMessage ? 1 : sentFlash ? 3 : 2;

  async function loadPreview(campaign: Campaign, channel?: string, prefetched?: AiPreview | null) {
    const preview =
      prefetched ??
      ((await getAiPreview(campaign.id)) as AiPreview);
    setAiPreview(preview);
    setMessageDraft(
      preview.message ??
        campaign.custom_message ??
        campaign.ai_defaults?.message ??
        "",
    );
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
    setMessages([]);
    setAiPreview(null);
    setTab("followup");
    try {
      const allowed = (channels.length > 0 ? channels : [...REVIEW_CHANNELS]).filter(
        (ch) => ch !== "voice",
      );
      const created = await createCampaign({
        name: `${action.title} follow-up`,
        campaign_type: action.campaign_type,
        channels_allowed: allowed.length > 0 ? allowed : [...REVIEW_CHANNELS],
        use_demo_audience: false,
        auto_schedule: false,
        expected_revenue: "500",
        tags: ["ai-followup", action.id],
        ...(action.custom_message ? { custom_message: action.custom_message } : {}),
      });
      const { ai_preview: prefetched, ...campaign } = created;
      setSelected(campaign);
      setActiveActionId(action.id);
      setCampaigns((prev) => [campaign, ...prev.filter((c) => c.id !== campaign.id)]);
      await loadPreview(campaign, undefined, prefetched ?? null);
      // Background only: full refresh was blocking Review customer (audience + metrics N+1).
      void refresh({ light: true }).catch(() => undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start follow-up");
    } finally {
      setBusy(false);
    }
  }

  /** Recent follow-ups: open message detail for the latest message in that campaign. */
  async function onSelectRecentFollowup(campaign: Campaign) {
    setBusy(true);
    setError(null);
    try {
      const msgs = await listCampaignMessages(campaign.id);
      if (msgs.length === 0) {
        setError("No messages for this follow-up");
        return;
      }
      const latest = [...msgs].sort((a, b) => {
        const ta = a.sent_at ?? a.scheduled_at ?? "";
        const tb = b.sent_at ?? b.scheduled_at ?? "";
        return tb.localeCompare(ta);
      })[0];
      // Do not set `selected` — that opens the Review customer dialog.
      setSelectedMessage({
        ...latest,
        campaign_name: campaign.name,
        campaign_type: campaign.campaign_type,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load message");
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
      setCampaigns((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      await loadPreview(updated, ch);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Channel update failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSend() {
    if (!selected || !canEditCampaign(selected) || !hasContact) return;
    const body = messageDraft.trim();
    if (!body) {
      setError("Message cannot be empty");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const patch: Record<string, unknown> = { custom_message: body };
      // Pin channel on send when user overrode it, or when AI chose voice (not offered).
      if (channelOverride || aiChannel === "voice") {
        patch.channels_allowed = [recommendedChannel];
      }
      const updated = await updateCampaign(selected.id, patch);
      setSelected(updated);
      setAiPreview((prev) => (prev ? { ...prev, message: body } : prev));
      await scheduleCampaign(selected.id);
      await processCampaign(selected.id);
      setSentFlash(true);
      const list = await refresh();
      const latest = list.find((x) => x.id === selected.id);
      if (latest) setSelected(latest);
      const msgs = await listCampaignMessages(selected.id);
      setMessages(msgs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Send failed");
    } finally {
      setBusy(false);
    }
  }

  /** Load campaign messages for the Messages tab (sent follow-ups grouped by type). */
  async function onLoadMessages() {
    // Messages tab: load all sent follow-ups and group by type
    const targets = campaigns.filter(
      (c) => c.status !== "draft" && c.status !== "cancelled",
    );
    if (targets.length === 0) {
      setTabMessages([]);
      setSelectedMessage(null);
      setSelectedMessageIds(new Set());
      setMessagesTypeFilter(null);
      setTab("messages");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const nested = await Promise.all(
        targets.map(async (c) => {
          const msgs = await listCampaignMessages(c.id);
          return msgs.map((m) => ({
            ...m,
            campaign_name: c.name,
            campaign_type: c.campaign_type,
          }));
        }),
      );
      const flat = nested.flat();
      setTabMessages(flat);
      setSelectedMessage(null);
      setSelectedMessageIds(new Set());
      setTab("messages");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load messages failed");
    } finally {
      setBusy(false);
    }
  }

  const visibleMessageIds = useMemo(
    () => messagesByType.flatMap((g) => g.items.map((m) => m.id)),
    [messagesByType],
  );

  const allVisibleSelected =
    visibleMessageIds.length > 0 &&
    visibleMessageIds.every((id) => selectedMessageIds.has(id));

  function toggleMessageSelected(id: string) {
    setSelectedMessageIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAllVisible() {
    setSelectedMessageIds((prev) => {
      if (allVisibleSelected) {
        const next = new Set(prev);
        for (const id of visibleMessageIds) next.delete(id);
        return next;
      }
      const next = new Set(prev);
      for (const id of visibleMessageIds) next.add(id);
      return next;
    });
  }

  async function onDeleteSelectedMessages() {
    const ids = [...selectedMessageIds];
    if (ids.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await deleteCampaignMessages(ids);
      const removed = new Set(ids);
      setTabMessages((prev) => prev.filter((m) => !removed.has(m.id)));
      setMessages((prev) => prev.filter((m) => !removed.has(m.id)));
      setSelectedMessage((prev) => (prev && removed.has(prev.id) ? null : prev));
      setSelectedMessageIds(new Set());
      setDeleteSelectedConfirm(false);
      // Recompute campaigns that still have messages so Recent follow-ups stays in sync.
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete messages failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="shrink-0">
        <h1 className="page-title">AI Customer Follow-up</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          SMS · Email · Voice — AI suggests who to contact and drafts the message
        </p>
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
          onClick={() => void onLoadMessages()}
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
          onClick={() => setTab("analytics")}
          className={`rounded-md px-3 py-1.5 text-sm ${
            tab === "analytics"
              ? "bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
              : "text-[var(--muted)] hover:bg-[var(--accent-soft)]"
          }`}
        >
          Analytics
        </button>
      </div>

      {error && (
        <p className="shrink-0 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      <div
        className={
          tab === "messages"
            ? "flex min-h-0 flex-1 flex-col overflow-hidden"
            : "asa-scroll min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain"
        }
      >
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

          <section className="mx-auto w-full max-w-2xl space-y-3">
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

            {recentSentFollowUps.length > 0 && (
              <div className="pt-2">
                <h3 className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                  Recent follow-ups
                </h3>
                <ul className="asa-scroll mt-2 max-h-40 space-y-1 overflow-y-auto overscroll-contain">
                  {recentSentFollowUps.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onSelectRecentFollowup(c)}
                        className={`w-full rounded-md px-3 py-2 text-left text-sm disabled:opacity-60 ${
                          selectedMessage?.campaign_id === c.id
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

        </div>
      )}

      {/* Portaled so dim covers header + chrome (escapes overflow-hidden shell) */}
      {portalReady &&
        selected &&
        tab === "followup" &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="followup-dialog-title"
            onClick={(e) => {
              if (e.target === e.currentTarget) closeFollowupDialog();
            }}
          >
            <section
              className="asa-scroll max-h-[min(90vh,720px)] w-full max-w-lg space-y-4 overflow-y-auto rounded-md border border-[var(--line)] bg-[var(--panel)] p-5 shadow-lg"
              onClick={(e) => e.stopPropagation()}
            >
              <div>
                <h2 id="followup-dialog-title" className="text-sm font-medium">
                  Review customer
                </h2>
              </div>

              <div className="space-y-2 text-sm">
                <p>
                  <span className="text-[var(--muted)]">Customer:</span>{" "}
                  {aiPreview?.customer_name
                    ? aiPreview.customer_name
                    : busy
                      ? "Loading…"
                      : "—"}
                </p>
                <p>
                  <span className="text-[var(--muted)]">Contact:</span>{" "}
                  {reviewContact ||
                    (recommendedChannel === "email" ? "No email" : "No phone")}
                </p>
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
                {(() => {
                  const reasons = (
                    aiPreview?.reasons ??
                    selected.ai_defaults?.reasons ??
                    []
                  ).filter(
                    (r) =>
                      !r.startsWith("channel=") &&
                      !r.startsWith("send_window=") &&
                      !r.startsWith("frequency="),
                  );
                  return reasons.length ? (
                    <p className="text-xs text-[var(--muted)]">{reasons.join(" · ")}</p>
                  ) : null;
                })()}
              </div>

              <div className="border-t border-[var(--line)] pt-4">
                <h2 className="text-sm font-medium">AI Message Preview</h2>

                <div className="mt-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs text-[var(--muted)]">Channel</p>
                    <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--accent)]">
                      AI recommends {recommendedChannel.toUpperCase()}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {reviewChannels.map((ch) => {
                      const backendAi =
                        aiPreview?.channel ?? selected.ai_defaults?.channel ?? "sms";
                      const isAi =
                        ch === (backendAi === "voice" ? "sms" : backendAi);
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
                  {!canEditCampaign(selected) && (
                    <p className="mt-1.5 text-[11px] text-[var(--muted)]">Channel is locked after send.</p>
                  )}
                </div>

                <div className="mt-3">
                  <label className="text-xs text-[var(--muted)]" htmlFor="ai-message-draft">
                    Message
                  </label>
                  {canEditCampaign(selected) ? (
                    <textarea
                      id="ai-message-draft"
                      value={messageDraft}
                      onChange={(e) => setMessageDraft(e.target.value)}
                      disabled={busy}
                      rows={5}
                      placeholder={busy ? "Generating…" : "AI message will appear here"}
                      className="mt-1.5 w-full resize-y whitespace-pre-wrap rounded-md border border-[var(--line)] bg-transparent p-3 text-sm outline-none focus:border-[var(--accent)] disabled:opacity-60"
                    />
                  ) : (
                    <div className="mt-1.5 whitespace-pre-wrap rounded-md border border-[var(--line)] p-3 text-sm text-[var(--muted)]">
                      {previewMessage ?? "No preview yet"}
                    </div>
                  )}
                  {canEditCampaign(selected) && (
                    <p className="mt-1.5 text-[11px] text-[var(--muted)]">
                      Edit the AI draft before send.
                    </p>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 border-t border-[var(--line)] pt-4">
                <button
                  type="button"
                  disabled={
                    busy || !previewMessage || !canEditCampaign(selected) || !hasContact
                  }
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
                  onClick={() => closeFollowupDialog()}
                  className="rounded-md border border-[var(--line)] px-3 py-2 text-sm disabled:opacity-60"
                >
                  Cancel
                </button>
                {sentFlash && (
                  <span className="text-xs font-medium text-[var(--accent)]">
                    Follow-up queued and processed
                  </span>
                )}
              </div>
            </section>
          </div>,
          document.body,
        )}

      {tab === "analytics" && summary && (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Metric label="Follow-ups" value={String(summary.campaigns)} />
            <Metric label="Sent" value={String(summary.sent)} />
            <Metric
              label="Appointment rate"
              value={`${(summary.appointment_rate * 100).toFixed(1)}%`}
            />
            <Metric label="Revenue" value={`$${Number(summary.revenue).toLocaleString()}`} />
          </div>

          <section className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
            <h2 className="text-sm font-medium">By channel</h2>
            <div className="mt-3 space-y-2">
              {Object.entries(summary.by_channel)
                .filter(([ch]) => ch !== "voice")
                .map(([ch, n]) => {
                  const max = Math.max(
                    ...Object.entries(summary.by_channel)
                      .filter(([k]) => k !== "voice")
                      .map(([, v]) => v),
                    1,
                  );
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
        </div>
      )}

      {tab === "messages" && (
        <section className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
          {(messageTypeChips.length > 0 || tabMessages.length > 0) && (
            <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setSelectedMessage(null);
                    setMessagesTypeFilter(null);
                  }}
                  className={`rounded-md border px-2.5 py-1 text-xs disabled:opacity-60 ${
                    messagesTypeFilter === null
                      ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                      : "border-[var(--line)] text-[var(--muted)] hover:bg-[var(--accent-soft)]"
                  }`}
                >
                  All ({tabMessages.length})
                </button>
                {messageTypeChips.map((chip) => (
                  <button
                    key={chip.type}
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setSelectedMessage(null);
                      setMessagesTypeFilter(chip.type);
                    }}
                    className={`rounded-md border px-2.5 py-1 text-xs capitalize disabled:opacity-60 ${
                      messagesTypeFilter === chip.type
                        ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                        : "border-[var(--line)] text-[var(--muted)] hover:bg-[var(--accent-soft)]"
                    }`}
                  >
                    {chip.label} ({chip.count})
                  </button>
                ))}
              </div>
              {tabMessages.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    disabled={busy || visibleMessageIds.length === 0}
                    onClick={toggleSelectAllVisible}
                    className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs text-[var(--muted)] hover:bg-[var(--accent-soft)] disabled:opacity-60"
                  >
                    {allVisibleSelected ? "Deselect all" : "Select all"}
                  </button>
                  <button
                    type="button"
                    disabled={busy || selectedMessageIds.size === 0}
                    onClick={() => setDeleteSelectedConfirm(true)}
                    className="rounded-md border border-red-300 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                  >
                    Delete{selectedMessageIds.size > 0 ? ` (${selectedMessageIds.size})` : ""}
                  </button>
                </div>
              )}
            </div>
          )}
          {tabMessages.length === 0 && !busy && (
            <p className="shrink-0 text-sm text-[var(--muted)]">
              {recentSentFollowUps.length === 0
                ? "Start a follow-up from the Follow-up tab to see messages"
                : "No messages yet — send a follow-up to queue messages"}
            </p>
          )}
          <div className="asa-scroll min-h-0 flex-1 space-y-2 overflow-y-auto overscroll-contain">
            {messagesByType.flatMap((group) =>
              group.items.map((m) => {
                const checked = selectedMessageIds.has(m.id);
                return (
                  <div
                    key={m.id}
                    className={`flex w-full items-start gap-2 rounded-md border bg-[var(--panel)] px-3 py-2 text-sm transition-colors ${
                      checked || selectedMessage?.id === m.id
                        ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                        : "border-[var(--line)] hover:border-[var(--accent)]"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={busy}
                      onChange={() => toggleMessageSelected(m.id)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`Select message ${m.channel} ${m.status}`}
                      className="mt-1 h-4 w-4 shrink-0 cursor-pointer accent-[var(--accent)] disabled:opacity-60"
                    />
                    <button
                      type="button"
                      onClick={() => setSelectedMessage(m)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <p className="font-medium uppercase tracking-wide">
                        {m.channel} · {m.status}
                      </p>
                      <p className="mt-0.5 text-[11px] text-[var(--muted)]">{m.campaign_name}</p>
                      <p className="mt-1 text-xs text-[var(--muted)] line-clamp-2">{m.body}</p>
                    </button>
                    {(m.sent_at || m.scheduled_at) && (
                      <span className="shrink-0 text-[11px] text-[var(--muted)]">
                        {m.sent_at
                          ? new Date(m.sent_at).toLocaleString()
                          : `scheduled ${new Date(m.scheduled_at!).toLocaleString()}`}
                      </span>
                    )}
                  </div>
                );
              }),
            )}
          </div>
        </section>
      )}

      {portalReady &&
        selectedMessage &&
        (tab === "messages" || tab === "followup") &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="message-detail-title"
            onClick={(e) => {
              if (e.target === e.currentTarget) setSelectedMessage(null);
            }}
          >
            <section
              className="asa-scroll max-h-[min(90vh,720px)] w-full max-w-lg space-y-4 overflow-y-auto rounded-md border border-[var(--line)] bg-[var(--panel)] p-5 shadow-lg"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 id="message-detail-title" className="text-sm font-medium">
                    {selectedMessage.channel === "voice"
                      ? "Voice call detail"
                      : selectedMessage.channel === "email"
                        ? "Email detail"
                        : selectedMessage.channel === "sms"
                          ? "SMS detail"
                          : "Message detail"}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedMessage(null)}
                  className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs text-[var(--muted)] hover:bg-[var(--accent-soft)]"
                >
                  Close
                </button>
              </div>

              <div className="space-y-2 text-sm">
                {selectedMessage.sent_at && (
                  <p>
                    <span className="text-[var(--muted)]">
                      {selectedMessage.channel === "voice" ? "Called:" : "Sent:"}
                    </span>{" "}
                    {new Date(selectedMessage.sent_at).toLocaleString()}
                  </p>
                )}
                {!selectedMessage.sent_at && selectedMessage.scheduled_at && (
                  <p>
                    <span className="text-[var(--muted)]">Scheduled:</span>{" "}
                    {new Date(selectedMessage.scheduled_at).toLocaleString()}
                  </p>
                )}
                {(selectedMessage.customer_name || selectedMessage.customer_id) && (
                  <p>
                    <span className="text-[var(--muted)]">Customer:</span>{" "}
                    {selectedMessage.customer_name || selectedMessage.customer_id}
                  </p>
                )}
              </div>

              <div className="border-t border-[var(--line)] pt-4">
                <p className="text-xs text-[var(--muted)]">
                  {selectedMessage.channel === "voice"
                    ? "Call script"
                    : selectedMessage.channel === "email"
                      ? "Text"
                      : "Message"}
                </p>
                <div className="mt-1.5 whitespace-pre-wrap rounded-md border border-[var(--line)] p-3 text-sm">
                  {selectedMessage.body ||
                    (selectedMessage.channel === "voice"
                      ? "(empty script)"
                      : selectedMessage.channel === "email"
                        ? "(empty text)"
                        : "(empty message)")}
                </div>
              </div>

              {selectedMessage.error && (
                <p className="text-xs text-red-600">{selectedMessage.error}</p>
              )}
            </section>
          </div>,
          document.body,
        )}

      {portalReady &&
        deleteSelectedConfirm &&
        createPortal(
          <div
            className="fixed inset-0 z-[110] flex items-center justify-center bg-black/50 p-4"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="delete-selected-messages-title"
            aria-describedby="delete-selected-messages-desc"
            onClick={(e) => {
              if (e.target === e.currentTarget && !busy) setDeleteSelectedConfirm(false);
            }}
          >
            <section
              className="w-full max-w-sm space-y-4 rounded-md border border-[var(--line)] bg-[var(--panel)] p-5 shadow-lg"
              onClick={(e) => e.stopPropagation()}
            >
              <div>
                <h2 id="delete-selected-messages-title" className="text-sm font-medium">
                  Delete selected messages?
                </h2>
                <p id="delete-selected-messages-desc" className="mt-1.5 text-sm text-[var(--muted)]">
                  This cannot be undone. {selectedMessageIds.size} selected message
                  {selectedMessageIds.size === 1 ? "" : "s"} will be permanently removed.
                </p>
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setDeleteSelectedConfirm(false)}
                  className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm text-[var(--muted)] hover:bg-[var(--accent-soft)] disabled:opacity-60"
                >
                  No
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void onDeleteSelectedMessages()}
                  className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  {busy ? "Deleting…" : "Yes"}
                </button>
              </div>
            </section>
          </div>,
          document.body,
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
