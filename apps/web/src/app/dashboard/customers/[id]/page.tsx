"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  addCommunication,
  createVehicle,
  CustomerDetail,
  getCustomerDetail,
  getVehicleDetail,
  RepairHistory,
  updateCustomer,
  Vehicle,
} from "@/lib/crm";
import { useAuth } from "@/lib/auth";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import {
  deleteMemory,
  listMemories,
  MemoryRecord,
  rememberMemory,
} from "@/lib/memory";
import { listSmsConversations, SmsConversation } from "@/lib/sms";
import { listVoiceCalls, VoiceCall } from "@/lib/calls";
import { listOpportunities, Opportunity } from "@/lib/revenue";

const AI_NOTE_CATEGORIES = [
  "customer_history",
  "customer_preferences",
  "communication_style",
  "previous_conversations",
  "repair_decisions",
  "declined_estimates",
  "appointment_behavior",
  "vehicle_history",
] as const;

function vehicleLabel(v: Vehicle): string {
  return `${v.year} ${v.make} ${v.model}`.trim();
}

type RepairWithVehicle = RepairHistory & { vehicle_label: string };

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const customerId = params.id;
  const { session, loading: authLoading } = useAuth();
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [repairs, setRepairs] = useState<RepairWithVehicle[]>([]);
  const [aiNotes, setAiNotes] = useState<MemoryRecord[]>([]);
  const [smsThreads, setSmsThreads] = useState<SmsConversation[]>([]);
  const [voiceCalls, setVoiceCalls] = useState<VoiceCall[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [editName, setEditName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editAddress, setEditAddress] = useState("");

  const [vin, setVin] = useState("");
  const [plate, setPlate] = useState("");
  const [year, setYear] = useState("2018");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [mileage, setMileage] = useState("0");

  const [channel, setChannel] = useState<"sms" | "phone" | "email" | "facebook">("sms");
  const [direction, setDirection] = useState<"incoming" | "outgoing">("outgoing");
  const [message, setMessage] = useState("");

  const [noteCategory, setNoteCategory] =
    useState<(typeof AI_NOTE_CATEGORIES)[number]>("customer_history");
  const [noteContent, setNoteContent] = useState("");
  const [noteBusy, setNoteBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [data, memories, smsAll, callsAll, oppsAll] = await Promise.all([
        getCustomerDetail(customerId),
        listMemories({ customer_id: customerId, limit: 50 }),
        listSmsConversations().catch(() => [] as SmsConversation[]),
        listVoiceCalls().catch(() => [] as VoiceCall[]),
        listOpportunities().catch(() => [] as Opportunity[]),
      ]);

      const historyBundles = await Promise.all(
        data.vehicles.map(async (v) => {
          try {
            const vd = await getVehicleDetail(v.id);
            return vd.repair_history.map((r) => ({
              ...r,
              vehicle_label: vehicleLabel(v),
            }));
          } catch {
            return [] as RepairWithVehicle[];
          }
        }),
      );

      const flatRepairs = historyBundles
        .flat()
        .sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
          return tb - ta;
        });

      setDetail(data);
      setRepairs(flatRepairs);
      setAiNotes(memories);
      setSmsThreads(smsAll.filter((c) => c.customer_id === customerId));
      setVoiceCalls(callsAll.filter((c) => c.customer_id === customerId));
      setOpportunities(oppsAll.filter((o) => o.customer_id === customerId));
      setEditName(data.customer.name);
      setEditPhone(formatPhoneInput(data.customer.phone ?? ""));
      setEditEmail(data.customer.email ?? "");
      setEditAddress(data.customer.address ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customer");
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    if (!authLoading && session && customerId) {
      void load();
    }
  }, [authLoading, session, customerId, load]);

  const recommendations = useMemo(() => {
    const fromRepairs = repairs
      .map((r) => r.recommendation?.trim())
      .filter((r): r is string => Boolean(r));
    const fromOpps = opportunities
      .filter((o) => o.status === "open")
      .map((o) => o.recommended_message || o.title);
    return [...new Set([...fromOpps, ...fromRepairs])].slice(0, 8);
  }, [repairs, opportunities]);

  async function onSaveCustomer(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await updateCustomer(customerId, {
        name: editName,
        phone: editPhone,
        email: editEmail,
        address: editAddress,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function onAddVehicle(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createVehicle(customerId, {
        vin,
        license_plate: plate || undefined,
        year: Number(year),
        make,
        model,
        mileage: Number(mileage),
      });
      setVin("");
      setPlate("");
      setMake("");
      setModel("");
      setMileage("0");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Vehicle create failed");
    }
  }

  async function onAddCommunication(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await addCommunication(customerId, { channel, direction, message });
      setMessage("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Communication failed");
    }
  }

  async function onAddNote(e: FormEvent) {
    e.preventDefault();
    if (!noteContent.trim()) return;
    setNoteBusy(true);
    setError(null);
    try {
      await rememberMemory({
        content: noteContent.trim(),
        memory_type: "customer",
        category: noteCategory,
        customer_id: customerId,
        importance: 0.8,
      });
      setNoteContent("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save AI note");
    } finally {
      setNoteBusy(false);
    }
  }

  async function onDeleteNote(id: string) {
    setNoteBusy(true);
    setError(null);
    try {
      await deleteMemory(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete AI note");
    } finally {
      setNoteBusy(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-[var(--muted)]">Loading customer…</p>;
  }

  if (!detail) {
    return <p className="text-sm text-red-700">{error ?? "Customer not found"}</p>;
  }

  return (
    <div className="space-y-8">
      <div>
        <Link href="/dashboard/customers" className="text-sm text-[var(--muted)] hover:text-[var(--accent)]">
          ← Customers
        </Link>
        <h1 className="page-title mt-2">{detail.customer.name}</h1>
        <p className="text-sm text-[var(--muted)]">
          Vehicles · repair history · conversations · AI notes · recommendations
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
        <h2 className="text-sm font-semibold">Profile</h2>
        <form onSubmit={onSaveCustomer} className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Customer name" value={editName} onChange={setEditName} required />
          <Field
            label="Phone"
            type="tel"
            value={editPhone}
            onChange={(v) => setEditPhone(formatPhoneInput(v))}
            placeholder={PHONE_PLACEHOLDER}
          />
          <Field label="Email" type="email" value={editEmail} onChange={setEditEmail} />
          <Field label="Address" value={editAddress} onChange={setEditAddress} />
          <div className="sm:col-span-2">
            <button type="submit" className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white">
              Save changes
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">Vehicles</h2>
        <div className="table-scroll">
          <table>
            <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
              <tr>
                <th className="px-4 py-3">Vehicle</th>
                <th className="px-4 py-3">VIN</th>
                <th className="px-4 py-3">Plate</th>
                <th className="px-4 py-3">Mileage</th>
              </tr>
            </thead>
            <tbody>
              {detail.vehicles.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-[var(--muted)]">
                    No vehicles yet
                  </td>
                </tr>
              ) : (
                detail.vehicles.map((v) => (
                  <tr key={v.id} className="border-t border-[var(--line)]">
                    <td className="px-4 py-3">
                      <Link href={`/dashboard/vehicles/${v.id}`} className="font-medium text-[var(--accent)]">
                        {vehicleLabel(v)}
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs">{v.vin}</td>
                    <td className="px-4 py-3 text-[var(--muted)]">{v.license_plate ?? "—"}</td>
                    <td className="px-4 py-3 text-[var(--muted)]">{v.mileage.toLocaleString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <form
          onSubmit={onAddVehicle}
          className="grid gap-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:grid-cols-3"
        >
          <Field label="VIN" value={vin} onChange={setVin} required />
          <Field label="License plate" value={plate} onChange={setPlate} />
          <Field label="Year" value={year} onChange={setYear} required />
          <Field label="Make" value={make} onChange={setMake} required />
          <Field label="Model" value={model} onChange={setModel} required />
          <Field label="Mileage" value={mileage} onChange={setMileage} required />
          <div className="sm:col-span-3">
            <button type="submit" className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white">
              Add vehicle
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">Repair history</h2>
        <p className="text-sm text-[var(--muted)]">
          Service work across all vehicles for this customer.
        </p>
        <div className="table-scroll">
          <table>
            <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
              <tr>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Vehicle</th>
                <th className="px-4 py-3">Service</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3">Cost</th>
              </tr>
            </thead>
            <tbody>
              {repairs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-[var(--muted)]">
                    No repair history yet
                  </td>
                </tr>
              ) : (
                repairs.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--line)]">
                    <td className="px-4 py-3 text-sm text-[var(--muted)]">
                      {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <Link
                        href={`/dashboard/vehicles/${r.vehicle_id}`}
                        className="text-[var(--accent)]"
                      >
                        {r.vehicle_label}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-sm font-medium">{r.service_type}</td>
                    <td className="px-4 py-3 text-sm text-[var(--muted)]">{r.description}</td>
                    <td className="px-4 py-3 text-sm">${r.cost}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">Conversations</h2>
        <p className="text-sm text-[var(--muted)]">
          SMS threads, voice calls, and logged CRM communications.
        </p>

        {(smsThreads.length > 0 || voiceCalls.length > 0) && (
          <div className="grid gap-3 sm:grid-cols-2">
            {smsThreads.map((t) => (
              <Link
                key={t.id}
                href="/dashboard/conversations?tab=sms"
                className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 hover:border-[var(--accent)]/40"
              >
                <div className="text-xs uppercase tracking-[0.08em] text-[var(--muted)]">SMS</div>
                <div className="mt-1 text-sm font-medium">{t.customer_phone}</div>
                <p className="mt-1 line-clamp-2 text-sm text-[var(--muted)]">
                  {t.owner_summary || t.reply_preview || t.last_intent || "Conversation"}
                </p>
                {t.last_message_at && (
                  <div className="mt-2 text-xs text-[var(--muted)]">
                    {new Date(t.last_message_at).toLocaleString()}
                  </div>
                )}
              </Link>
            ))}
            {voiceCalls.map((c) => (
              <Link
                key={c.id}
                href="/dashboard/conversations?tab=calls"
                className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 hover:border-[var(--accent)]/40"
              >
                <div className="text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                  Voice · {c.status}
                </div>
                <div className="mt-1 text-sm font-medium">{c.caller_phone}</div>
                <p className="mt-1 line-clamp-2 text-sm text-[var(--muted)]">
                  {c.owner_summary || c.call_summary || c.last_intent || "Call"}
                </p>
                {c.started_at && (
                  <div className="mt-2 text-xs text-[var(--muted)]">
                    {new Date(c.started_at).toLocaleString()}
                  </div>
                )}
              </Link>
            ))}
          </div>
        )}

        <div className="space-y-3">
          {detail.communications.length === 0 &&
          smsThreads.length === 0 &&
          voiceCalls.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No conversations yet</p>
          ) : (
            detail.communications.map((c) => (
              <div key={c.id} className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                  <span>{c.channel}</span>
                  <span>·</span>
                  <span>{c.direction}</span>
                  {c.created_at && (
                    <>
                      <span>·</span>
                      <span>{new Date(c.created_at).toLocaleString()}</span>
                    </>
                  )}
                </div>
                <p className="mt-2 text-sm">{c.message}</p>
              </div>
            ))
          )}
        </div>

        <form
          onSubmit={onAddCommunication}
          className="grid gap-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:grid-cols-2"
        >
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Channel</span>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value as typeof channel)}
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
            >
              <option value="sms">SMS</option>
              <option value="phone">Phone</option>
              <option value="email">Email</option>
              <option value="facebook">Facebook</option>
            </select>
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Direction</span>
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value as typeof direction)}
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
            >
              <option value="outgoing">Outgoing</option>
              <option value="incoming">Incoming</option>
            </select>
          </label>
          <label className="block space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Message</span>
            <textarea
              value={message}
              required
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
            />
          </label>
          <div className="sm:col-span-2">
            <button type="submit" className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white">
              Log communication
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">AI notes</h2>
        <p className="text-sm text-[var(--muted)]">
          Long-term memory — preferences, decisions, and shop context for this customer.
        </p>
        <div className="space-y-3">
          {aiNotes.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No AI notes yet</p>
          ) : (
            aiNotes.map((row) => (
              <div key={row.id} className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
                <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                  <span>{row.category.replaceAll("_", " ")}</span>
                  <span>·</span>
                  <span>importance {row.importance.toFixed(2)}</span>
                  {row.created_at && (
                    <>
                      <span>·</span>
                      <span>{new Date(row.created_at).toLocaleString()}</span>
                    </>
                  )}
                  <button
                    type="button"
                    disabled={noteBusy}
                    onClick={() => void onDeleteNote(row.id)}
                    className="ml-auto text-xs normal-case tracking-normal text-red-600 disabled:opacity-60"
                  >
                    Delete
                  </button>
                </div>
                <p className="mt-2 text-sm">{row.content}</p>
              </div>
            ))
          )}
        </div>

        <form
          onSubmit={onAddNote}
          className="grid gap-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:grid-cols-2"
        >
          <label className="block space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Category</span>
            <select
              value={noteCategory}
              onChange={(e) =>
                setNoteCategory(e.target.value as (typeof AI_NOTE_CATEGORIES)[number])
              }
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
            >
              {AI_NOTE_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Note</span>
            <textarea
              value={noteContent}
              required
              onChange={(e) => setNoteContent(e.target.value)}
              rows={3}
              placeholder="Prefers morning appointments, declined rear differential…"
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
            />
          </label>
          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={noteBusy}
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              Add AI note
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">Recommendations</h2>
        <p className="text-sm text-[var(--muted)]">
          From open revenue opportunities and prior repair recommendations.
        </p>
        {recommendations.length === 0 && opportunities.length === 0 ? (
          <p className="text-sm text-[var(--muted)]">No recommendations yet</p>
        ) : (
          <ul className="space-y-2">
            {opportunities
              .filter((o) => o.status === "open")
              .map((o) => (
                <li
                  key={o.id}
                  className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-sm font-medium">{o.title}</span>
                    <span className="text-xs text-[var(--muted)]">
                      {o.vehicle_label ?? "Vehicle TBD"} · contact{" "}
                      {new Date(o.recommended_contact_date).toLocaleDateString()}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-[var(--muted)]">{o.reason}</p>
                  {o.recommended_message && (
                    <p className="mt-2 text-sm">{o.recommended_message}</p>
                  )}
                </li>
              ))}
            {recommendations
              .filter((text) => !opportunities.some((o) => o.recommended_message === text || o.title === text))
              .map((text) => (
                <li
                  key={text}
                  className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--background)]/60 px-4 py-3 text-sm"
                >
                  {text}
                </li>
              ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
      />
    </label>
  );
}
