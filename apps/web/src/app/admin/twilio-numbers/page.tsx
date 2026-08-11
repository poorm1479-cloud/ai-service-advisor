"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell, Panel, Stat } from "@/components/admin/AdminShell";
import {
  assignAdminOrganizationTwilioNumber,
  clearAdminOrganizationTwilioNumber,
  getAdminOrganizations,
  getAdminSettings,
  OrganizationsResponse,
  ShopOrgRow,
  statusTone,
  streamAdminOrganizations,
  updateAdminSettings,
} from "@/lib/admin";

const POLL_MS = 3000;

type NumberFilter = "all" | "assigned" | "unassigned";

type RemoveTarget = {
  shopId: string;
  shopName: string;
  phone: string | null;
};

type CenterAlert = {
  tone: "success" | "error";
  title: string;
  body: string;
};

function hasTwilioNumber(s: ShopOrgRow) {
  return Boolean(s.twilio_phone_e164 || s.sms_phone_e164 || s.voice_phone_e164);
}

function primaryNumber(s: ShopOrgRow) {
  return s.twilio_phone_e164 || s.sms_phone_e164 || s.voice_phone_e164 || null;
}

export default function AdminTwilioNumbersPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <TwilioNumbersBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function TwilioNumbersBody({ accessToken }: { accessToken: string }) {
  const [data, setData] = useState<OrganizationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<NumberFilter>("all");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [actionId, setActionId] = useState<string | null>(null);
  const [manualPhone, setManualPhone] = useState<Record<string, string>>({});
  const [removeTarget, setRemoveTarget] = useState<RemoveTarget | null>(null);
  const [centerAlert, setCenterAlert] = useState<CenterAlert | null>(null);
  const [autoProvision, setAutoProvision] = useState<boolean | null>(null);
  const [autoProvisionBusy, setAutoProvisionBusy] = useState(false);

  const applyData = useCallback((next: OrganizationsResponse) => {
    setData((prev) => {
      if (prev?.generated_at && next.generated_at) {
        const prevTs = Date.parse(prev.generated_at);
        const nextTs = Date.parse(next.generated_at);
        if (Number.isFinite(prevTs) && Number.isFinite(nextTs) && nextTs < prevTs) {
          return prev;
        }
      }
      return next;
    });
    setLive(true);
    setError(null);
  }, []);

  const loadSettings = useCallback(
    async (quiet = false) => {
      try {
        const settings = await getAdminSettings(accessToken);
        setAutoProvision(Boolean(settings.editable.twilio_auto_provision_numbers));
      } catch (err) {
        if (!quiet) {
          setError(err instanceof Error ? err.message : "Failed to load settings");
        }
      }
    },
    [accessToken],
  );

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        applyData(await getAdminOrganizations(accessToken));
      } catch (err) {
        if (!quiet) {
          setLive(false);
          setError(err instanceof Error ? err.message : "Failed to load Twilio numbers");
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [accessToken, applyData],
  );

  useEffect(() => {
    void load(false);
    void loadSettings(false);
    const id = window.setInterval(() => {
      void load(true);
      void loadSettings(true);
    }, POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") {
        void load(true);
        void loadSettings(true);
      }
    };
    const onRefresh = () => void load(true);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("admin:shops-refresh", onRefresh);
    window.addEventListener("focus", onRefresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("admin:shops-refresh", onRefresh);
      window.removeEventListener("focus", onRefresh);
    };
  }, [load, loadSettings]);

  useEffect(() => {
    const stop = streamAdminOrganizations(
      accessToken,
      (next) => applyData(next),
      () => {
        /* polling keeps data fresh */
      },
      () => setLive(true),
    );
    return stop;
  }, [accessToken, applyData]);

  const stats = useMemo(() => {
    const shops = data?.shops ?? [];
    const assigned = shops.filter(hasTwilioNumber).length;
    return {
      total: shops.length,
      assigned,
      unassigned: shops.length - assigned,
    };
  }, [data]);

  const filtered = useMemo(() => {
    const shops = data?.shops ?? [];
    const q = query.trim().toLowerCase();
    return shops
      .filter((s) => {
        const assigned = hasTwilioNumber(s);
        if (filter === "assigned" && !assigned) return false;
        if (filter === "unassigned" && assigned) return false;
        if (!q) return true;
        const phone = primaryNumber(s) ?? "";
        return (
          s.shop_name.toLowerCase().includes(q) ||
          s.shop_slug.toLowerCase().includes(q) ||
          s.plan_name.toLowerCase().includes(q) ||
          s.status.toLowerCase().includes(q) ||
          phone.toLowerCase().includes(q) ||
          (s.sms_phone_e164 ?? "").toLowerCase().includes(q) ||
          (s.voice_phone_e164 ?? "").toLowerCase().includes(q)
        );
      })
      .sort((a, b) => {
        const aHas = Number(hasTwilioNumber(a));
        const bHas = Number(hasTwilioNumber(b));
        if (aHas !== bHas) return bHas - aHas;
        return a.shop_name.localeCompare(b.shop_name);
      });
  }, [data, filter, query]);

  async function onToggleAutoProvision(next: boolean) {
    setAutoProvisionBusy(true);
    setError(null);
    setMessage(null);
    const previous = autoProvision;
    setAutoProvision(next);
    try {
      const result = await updateAdminSettings(accessToken, {
        twilio_auto_provision_numbers: next,
      });
      setAutoProvision(Boolean(result.editable.twilio_auto_provision_numbers));
      setMessage(
        next
          ? "Auto-create Twilio number on account creation enabled"
          : "Auto-create Twilio number on account creation disabled",
      );
    } catch (err) {
      setAutoProvision(previous);
      setError(err instanceof Error ? err.message : "Failed to update setting");
    } finally {
      setAutoProvisionBusy(false);
    }
  }

  async function onAssignManual(shopId: string) {
    const phone = (manualPhone[shopId] || "").trim();
    if (!phone) {
      setError("Enter an E.164 number (e.g. +12065550100)");
      setCenterAlert({
        tone: "error",
        title: "Missing number",
        body: "Enter an E.164 number already on the Twilio account (e.g. +12065550100).",
      });
      return;
    }
    setActionId(shopId);
    setError(null);
    setMessage(null);
    try {
      const result = await assignAdminOrganizationTwilioNumber(accessToken, shopId, phone);
      const assigned = result.twilio_phone_e164 || phone;
      let okMsg = `Assigned ${assigned}`;
      if (result.webhooks_configured === false && result.webhooks_error) {
        okMsg += ` (webhook warning: ${result.webhooks_error})`;
      } else if (result.webhooks_configured) {
        okMsg += " — Twilio Voice/SMS webhooks linked to this API";
      }
      setMessage(okMsg);
      setManualPhone((prev) => {
        const next = { ...prev };
        delete next[shopId];
        return next;
      });
      setCenterAlert({
        tone: "success",
        title: "Number assigned",
        body: okMsg,
      });
      await load(true);
      window.dispatchEvent(new Event("admin:shops-refresh"));
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Assign failed";
      setError(errMsg);
      setCenterAlert({
        tone: "error",
        title: "Assign failed",
        body: errMsg,
      });
    } finally {
      setActionId(null);
    }
  }

  function openRemoveConfirm(shop: ShopOrgRow) {
    setError(null);
    setMessage(null);
    setRemoveTarget({
      shopId: shop.shop_id,
      shopName: shop.shop_name,
      phone: primaryNumber(shop),
    });
  }

  async function confirmRemove() {
    if (!removeTarget) return;
    const { shopId, shopName, phone } = removeTarget;
    setActionId(shopId);
    setError(null);
    setMessage(null);
    try {
      const result = await clearAdminOrganizationTwilioNumber(accessToken, shopId);
      const prev = result.previous_twilio_phone_e164 || phone || "number";
      const okMsg = `Unassigned ${prev} from ${shopName}. Number kept on Twilio account.`;
      setMessage(okMsg);
      setRemoveTarget(null);
      setCenterAlert({
        tone: "success",
        title: "Number unassigned",
        body: okMsg,
      });
      await load(true);
      window.dispatchEvent(new Event("admin:shops-refresh"));
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Remove failed";
      setError(errMsg);
      setRemoveTarget(null);
      setCenterAlert({
        tone: "error",
        title: "Remove failed",
        body: errMsg,
      });
    } finally {
      setActionId(null);
    }
  }

  if (error && !data) {
    return <p className="text-sm text-red-700">{error}</p>;
  }
  if (!data) {
    return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;
  }

  const removing = Boolean(removeTarget && actionId === removeTarget.shopId);
  const autoOn = autoProvision === true;

  return (
    <div className="flex h-[calc(100dvh-7.25rem)] flex-col gap-4 overflow-hidden sm:h-[calc(100dvh-7.75rem)] md:h-[calc(100dvh-9.25rem)] md:gap-5">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-[var(--muted)]">
          Shop Twilio SMS/Voice channel assignment — enter an E.164 number already on the Twilio account
        </p>
        <span
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
            live
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-[var(--line)] bg-[var(--background)] text-[var(--muted)]"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-500" : "bg-[var(--muted)]"}`}
          />
          {live ? "Live" : "Connecting"}
        </span>
      </div>

      <Panel title="Account creation" className="shrink-0">
        <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">Auto-create Twilio number on account creation</p>
            <p className="mt-1 text-xs text-[var(--muted)]">
              When enabled, new shop signups automatically receive an SMS/Voice number.
              Manual assign on this page still works when disabled.
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={autoOn}
            aria-label="Auto-create Twilio number on account creation"
            disabled={autoProvision === null || autoProvisionBusy}
            onClick={() => void onToggleAutoProvision(!autoOn)}
            className={`relative inline-flex h-7 w-12 shrink-0 items-center rounded-full border transition-colors disabled:opacity-50 ${
              autoOn
                ? "border-emerald-300 bg-emerald-500"
                : "border-[var(--line)] bg-[var(--background)]"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 rounded-full bg-white shadow transition-transform ${
                autoOn ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
        </div>
        <div className="border-t border-[var(--line)] px-5 py-2 text-xs text-[var(--muted)]">
          {autoProvision === null
            ? "Loading setting…"
            : autoOn
              ? "Status: enabled — new accounts get a number automatically"
              : "Status: disabled — new accounts start without a number"}
          {autoProvisionBusy ? " · Saving…" : null}
        </div>
      </Panel>

      <section className="grid shrink-0 gap-3 sm:grid-cols-3">
        <Stat label="Shops" value={String(stats.total)} />
        <Stat label="Numbers assigned" value={String(stats.assigned)} />
        <Stat label="Not assigned" value={String(stats.unassigned)} />
      </section>

      {error ? <p className="shrink-0 text-sm text-red-700">{error}</p> : null}
      {message ? <p className="shrink-0 text-sm text-emerald-700">{message}</p> : null}

      <Panel
        className="flex min-h-0 flex-1 flex-col"
        title={`Twilio numbers (${filtered.length})`}
        action={
          <div className="flex flex-nowrap items-center gap-2">
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as NumberFilter)}
              className="shrink-0 rounded-md border border-[var(--line)] bg-white px-2 py-1.5 text-sm"
              aria-label="Filter by assignment"
            >
              <option value="all">All shops</option>
              <option value="assigned">Assigned</option>
              <option value="unassigned">Not assigned</option>
            </select>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search shop or number…"
              className="w-44 shrink-0 rounded-md border border-[var(--line)] px-3 py-1.5 text-sm sm:w-56"
            />
          </div>
        }
      >
        <div className="asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 z-10 border-b border-[var(--line)] bg-[var(--background)] text-[var(--muted)]">
              <tr>
                <th className="px-5 py-2 font-medium">Shop</th>
                <th className="px-5 py-2 font-medium">Plan</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Number status</th>
                <th className="px-5 py-2 font-medium">Twilio number</th>
                <th className="px-5 py-2 font-medium">Channels</th>
                <th className="px-5 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const assigned = hasTwilioNumber(s);
                const phone = primaryNumber(s);
                const rowBusy = actionId === s.shop_id || busy;
                const splitChannels =
                  Boolean(s.sms_phone_e164) &&
                  Boolean(s.voice_phone_e164) &&
                  s.sms_phone_e164 !== s.voice_phone_e164;

                return (
                  <tr
                    key={s.shop_id}
                    className="border-b border-[var(--line)] align-top hover:bg-[var(--background)]"
                  >
                    <td className="px-5 py-3">
                      <Link
                        href={`/admin/shops/${s.shop_id}`}
                        className="font-medium hover:underline"
                      >
                        {s.shop_name}
                      </Link>
                      <div className="font-mono text-xs text-[var(--muted)]">{s.shop_slug}</div>
                    </td>
                    <td className="px-5 py-3">{s.plan_name}</td>
                    <td className={`px-5 py-3 capitalize ${statusTone(s.status)}`}>{s.status}</td>
                    <td className="px-5 py-3">
                      {assigned ? (
                        <span className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          Assigned
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                          <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                          Not assigned
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3">
                      {phone ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-sm">{phone}</span>
                          <button
                            type="button"
                            className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[11px] text-[var(--muted)] hover:text-[var(--foreground)]"
                            onClick={() => void navigator.clipboard.writeText(phone)}
                          >
                            Copy
                          </button>
                        </div>
                      ) : (
                        <span className="text-[var(--muted)]">—</span>
                      )}
                    </td>
                    <td className="px-5 py-3 font-mono text-xs text-[var(--muted)]">
                      {splitChannels ? (
                        <div className="space-y-0.5">
                          <div>SMS: {s.sms_phone_e164}</div>
                          <div>Voice: {s.voice_phone_e164}</div>
                        </div>
                      ) : assigned ? (
                        <span>SMS + Voice</span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-5 py-3">
                      {assigned ? (
                        <button
                          type="button"
                          disabled={rowBusy}
                          onClick={() => openRemoveConfirm(s)}
                          className="rounded-md border border-[var(--line)] px-2 py-1 text-xs text-red-700 disabled:opacity-50"
                          title="Unassign from shop in the database only (Twilio account keeps the number)"
                        >
                          {actionId === s.shop_id ? "Removing…" : "Remove"}
                        </button>
                      ) : (
                        <div className="flex min-w-[12rem] gap-1">
                          <input
                            value={manualPhone[s.shop_id] ?? ""}
                            onChange={(e) =>
                              setManualPhone((prev) => ({
                                ...prev,
                                [s.shop_id]: e.target.value,
                              }))
                            }
                            placeholder="+1…"
                            className="min-w-0 flex-1 rounded-md border border-[var(--line)] px-2 py-1 font-mono text-xs"
                            disabled={rowBusy}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                void onAssignManual(s.shop_id);
                              }
                            }}
                          />
                          <button
                            type="button"
                            disabled={rowBusy}
                            onClick={() => void onAssignManual(s.shop_id)}
                            className="rounded-md border border-[var(--line)] px-2 py-1 text-xs disabled:opacity-50"
                            title="Assign an E.164 number already on this Twilio account"
                          >
                            Set
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-[var(--muted)]">
                    No shops match this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {removeTarget ? (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="remove-twilio-title"
          aria-describedby="remove-twilio-desc"
          onClick={() => {
            if (!removing) setRemoveTarget(null);
          }}
        >
          <div
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="remove-twilio-title" className="text-base font-semibold">
                Remove Twilio number?
              </h2>
              <p id="remove-twilio-desc" className="mt-2 text-sm text-[var(--muted)]">
                Unassign{" "}
                <span className="font-mono text-[var(--foreground)]">
                  {removeTarget.phone || "—"}
                </span>{" "}
                from{" "}
                <span className="font-medium text-[var(--foreground)]">{removeTarget.shopName}</span>
                .
              </p>
              <p className="mt-2 text-sm text-[var(--muted)]">
                Unassigns the number from this shop in our database only. The Twilio
                account is not contacted — the number stays purchased and can be
                reassigned later.
              </p>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                disabled={removing}
                onClick={() => setRemoveTarget(null)}
                className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={removing}
                onClick={() => void confirmRemove()}
                className="rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-800 disabled:opacity-50"
              >
                {removing ? "Removing…" : "Remove"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {centerAlert ? (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="twilio-alert-title"
          aria-describedby="twilio-alert-body"
          onClick={() => setCenterAlert(null)}
        >
          <div
            className="w-full max-w-sm space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2
                id="twilio-alert-title"
                className={`text-base font-semibold ${
                  centerAlert.tone === "error" ? "text-red-800" : "text-emerald-800"
                }`}
              >
                {centerAlert.title}
              </h2>
              <p id="twilio-alert-body" className="mt-2 text-sm text-[var(--muted)]">
                {centerAlert.body}
              </p>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => setCenterAlert(null)}
                className="rounded-md border border-[var(--line)] bg-[var(--background)] px-3 py-1.5 text-sm font-medium"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
