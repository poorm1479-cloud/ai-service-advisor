"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createCustomer,
  Customer,
  getCustomerDetail,
  getVehicleDetail,
  RepairHistory,
  searchCustomers,
  Vehicle,
} from "@/lib/crm";
import { listAppointments, Appointment } from "@/lib/appointments";
import { listOpportunities, Opportunity } from "@/lib/revenue";
import { useAuth } from "@/lib/auth";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

type CreateMode = "known" | "unknown" | null;

type CustomerRow = {
  customer: Customer;
  vehicles: Vehicle[];
  lastService: { label: string; at: string | null } | null;
  nextService: { label: string; at: string | null } | null;
  status: "Active" | "Scheduled" | "Follow-up" | "New";
};

function vehicleLabel(v: Vehicle): string {
  return `${v.year} ${v.make} ${v.model}`.trim();
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString();
}

function pickLatestRepair(repairs: RepairHistory[]): RepairHistory | null {
  if (repairs.length === 0) return null;
  return [...repairs].sort((a, b) => {
    const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
    const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
    return tb - ta;
  })[0];
}

function deriveStatus(
  customer: Customer,
  nextAppt: Appointment | undefined,
  openOpp: Opportunity | undefined,
  lastRepair: RepairHistory | null,
): CustomerRow["status"] {
  if (openOpp) return "Follow-up";
  if (nextAppt) return "Scheduled";
  if (lastRepair?.created_at) return "Active";
  const created = customer.created_at ? new Date(customer.created_at).getTime() : 0;
  const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  if (created > weekAgo) return "New";
  return "Active";
}

async function enrichCustomer(
  customer: Customer,
  appointments: Appointment[],
  opportunities: Opportunity[],
): Promise<CustomerRow> {
  const detail = await getCustomerDetail(customer.id);
  const histories = await Promise.all(
    detail.vehicles.map(async (v) => {
      try {
        const vd = await getVehicleDetail(v.id);
        return vd.repair_history;
      } catch {
        return [] as RepairHistory[];
      }
    }),
  );
  const repairs = histories.flat();
  const lastRepair = pickLatestRepair(repairs);

  const now = Date.now();
  const nextAppt = appointments
    .filter((a) => a.customer_id === customer.id && new Date(a.start).getTime() >= now)
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())[0];

  const openOpp = opportunities
    .filter((o) => o.customer_id === customer.id && o.status === "open")
    .sort(
      (a, b) =>
        new Date(a.recommended_contact_date).getTime() -
        new Date(b.recommended_contact_date).getTime(),
    )[0];

  let nextService: CustomerRow["nextService"] = null;
  if (nextAppt) {
    nextService = {
      label: nextAppt.repair_type || "Appointment",
      at: nextAppt.start,
    };
  } else if (openOpp) {
    nextService = {
      label: openOpp.title,
      at: openOpp.recommended_contact_date,
    };
  }

  return {
    customer,
    vehicles: detail.vehicles,
    lastService: lastRepair
      ? {
          label: lastRepair.service_type || lastRepair.description,
          at: lastRepair.created_at ?? null,
        }
      : null,
    nextService,
    status: deriveStatus(customer, nextAppt, openOpp, lastRepair),
  };
}

function matchesQuery(row: CustomerRow, q: string): boolean {
  const needle = q.trim().toLowerCase();
  if (!needle) return true;
  const { customer, vehicles } = row;
  if (customer.name.toLowerCase().includes(needle)) return true;
  if (customer.phone?.toLowerCase().includes(needle)) return true;
  return vehicles.some((v) => {
    const vin = v.vin.toLowerCase();
    const label = vehicleLabel(v).toLowerCase();
    const plate = (v.license_plate ?? "").toLowerCase();
    return vin.includes(needle) || label.includes(needle) || plate.includes(needle);
  });
}

const STATUS_CLASS: Record<CustomerRow["status"], string> = {
  Active: "bg-emerald-50 text-emerald-800",
  Scheduled: "bg-sky-50 text-sky-800",
  "Follow-up": "bg-amber-50 text-amber-900",
  New: "bg-slate-100 text-slate-700",
};

export default function CustomersPage() {
  const { session, loading: authLoading } = useAuth();
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [rows, setRows] = useState<CustomerRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [createMode, setCreateMode] = useState<CreateMode>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const rangeStart = new Date();
      rangeStart.setMonth(rangeStart.getMonth() - 1);
      const rangeEnd = new Date();
      rangeEnd.setMonth(rangeEnd.getMonth() + 3);

      const [customers, appointments, opportunities] = await Promise.all([
        searchCustomers(),
        listAppointments(rangeStart.toISOString(), rangeEnd.toISOString()).catch(
          () => [] as Appointment[],
        ),
        listOpportunities({ status: "open" }).catch(() => [] as Opportunity[]),
      ]);

      const enriched = await Promise.all(
        customers.map((c) => enrichCustomer(c, appointments, opportunities)),
      );
      setRows(enriched);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customers");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && session) {
      void load();
    }
  }, [authLoading, session]);

  const visible = useMemo(
    () => rows.filter((r) => matchesQuery(r, appliedQuery)),
    [rows, appliedQuery],
  );

  function onSearch(e: FormEvent) {
    e.preventDefault();
    setAppliedQuery(query);
  }

  async function onCreateKnown(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await createCustomer({
        name: name.trim(),
        phone: phone || undefined,
        email: email || undefined,
      });
      setName("");
      setPhone("");
      setEmail("");
      setCreateMode(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create customer");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Customers</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Vehicle-centered CRM — customers, vehicles, and service timing
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreateMode((m) => (m ? null : "known"))}
          className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
        >
          {createMode ? "Close" : "Add"}
        </button>
      </div>

      <form onSubmit={onSearch} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search customer name, phone, VIN, vehicle…"
          className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
        />
        <button
          type="submit"
          className="shrink-0 rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-2 text-sm"
        >
          Search
        </button>
      </form>

      {createMode !== null && (
        <section className="space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
          <div>
            <h2 className="text-sm font-semibold">How are you adding this visit?</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Create a known customer, or start an unknown walk-in without a customer record.
            </p>
          </div>

          <div className="grid gap-2 sm:grid-cols-2">
            <ModeOption
              active={createMode === "known"}
              label="Known customer"
              description="Create or look up by name / phone"
              onClick={() => setCreateMode("known")}
            />
            <ModeOption
              active={createMode === "unknown"}
              label="Unknown walk-in"
              description="No customer required — start from walk-ins"
              onClick={() => setCreateMode("unknown")}
            />
          </div>

          {createMode === "known" && (
            <form onSubmit={onCreateKnown} className="grid gap-3 sm:grid-cols-2">
              <Field label="Customer name" value={name} onChange={setName} required />
              <Field
                label="Phone"
                type="tel"
                value={phone}
                onChange={(v) => setPhone(formatPhoneInput(v))}
                placeholder={PHONE_PLACEHOLDER}
              />
              <Field label="Email (optional)" type="email" value={email} onChange={setEmail} />
              <div className="flex items-end sm:col-span-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {saving ? "Saving…" : "Create customer"}
                </button>
              </div>
            </form>
          )}

          {createMode === "unknown" && (
            <div className="rounded-lg border border-dashed border-[var(--line)] bg-[var(--background)]/60 p-3 text-sm">
              <p className="text-[var(--muted)]">
                Skip the customer record. Start a vehicle-first walk-in without a name or phone.
              </p>
              <Link
                href="/dashboard/walk-ins"
                className="mt-3 inline-block rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
              >
                Open walk-ins
              </Link>
            </div>
          )}
        </section>
      )}

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <div className="table-scroll">
        <table>
          <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3 font-medium">Customer</th>
              <th className="px-4 py-3 font-medium">Vehicles</th>
              <th className="px-4 py-3 font-medium">Last Service</th>
              <th className="px-4 py-3 font-medium">Next Service</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-[var(--muted)]">
                  Loading…
                </td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-[var(--muted)]">
                  No customers found
                </td>
              </tr>
            ) : (
              visible.map((row) => (
                <tr
                  key={row.customer.id}
                  className="border-t border-[var(--line)] hover:bg-[var(--accent-soft)]/40"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium">{row.customer.name}</div>
                    <div className="text-xs text-[var(--muted)]">
                      {row.customer.phone ?? "No phone"}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {row.vehicles.length === 0 ? (
                      <span className="text-[var(--muted)]">—</span>
                    ) : (
                      <div className="space-y-0.5">
                        {row.vehicles.slice(0, 2).map((v) => (
                          <div key={v.id}>
                            <span>{vehicleLabel(v)}</span>
                            <span className="ml-1 font-mono text-[10px] text-[var(--muted)]">
                              {v.vin.slice(-6)}
                            </span>
                          </div>
                        ))}
                        {row.vehicles.length > 2 && (
                          <div className="text-xs text-[var(--muted)]">
                            +{row.vehicles.length - 2} more
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {row.lastService ? (
                      <>
                        <div>{row.lastService.label}</div>
                        <div className="text-xs text-[var(--muted)]">
                          {formatDate(row.lastService.at)}
                        </div>
                      </>
                    ) : (
                      <span className="text-[var(--muted)]">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {row.nextService ? (
                      <>
                        <div>{row.nextService.label}</div>
                        <div className="text-xs text-[var(--muted)]">
                          {formatDate(row.nextService.at)}
                        </div>
                      </>
                    ) : (
                      <span className="text-[var(--muted)]">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${STATUS_CLASS[row.status]}`}
                    >
                      {row.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/dashboard/customers/${row.customer.id}`}
                      className="text-sm font-medium text-[var(--accent)]"
                    >
                      Open
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ModeOption({
  active,
  label,
  description,
  onClick,
}: {
  active: boolean;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-lg border px-3 py-3 text-left transition ${
        active
          ? "border-[var(--accent)] bg-[var(--accent-soft)]/50"
          : "border-[var(--line)] bg-[var(--background)]/60 hover:border-[var(--accent)]/50"
      }`}
    >
      <div className="text-sm font-medium">{label}</div>
      <div className="mt-1 text-xs text-[var(--muted)]">{description}</div>
    </button>
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
