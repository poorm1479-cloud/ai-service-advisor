"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { addRepairHistory, getVehicleDetail, VehicleDetail } from "@/lib/crm";
import { useAuth } from "@/lib/auth";

export default function VehicleDetailPage() {
  const params = useParams<{ id: string }>();
  const vehicleId = params.id;
  const { session, loading: authLoading } = useAuth();
  const [detail, setDetail] = useState<VehicleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [serviceType, setServiceType] = useState("");
  const [description, setDescription] = useState("");
  const [cost, setCost] = useState("0");
  const [recommendation, setRecommendation] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setDetail(await getVehicleDetail(vehicleId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load vehicle");
    } finally {
      setLoading(false);
    }
  }, [vehicleId]);

  useEffect(() => {
    if (!authLoading && session && vehicleId) {
      void load();
    }
  }, [authLoading, session, vehicleId, load]);

  async function onAddHistory(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await addRepairHistory(vehicleId, {
        service_type: serviceType,
        description,
        cost: Number(cost),
        recommendation: recommendation || undefined,
      });
      setServiceType("");
      setDescription("");
      setCost("0");
      setRecommendation("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add history");
    }
  }

  if (loading) {
    return <p className="text-sm text-[var(--muted)]">Loading vehicle…</p>;
  }

  if (!detail) {
    return <p className="text-sm text-red-700">{error ?? "Vehicle not found"}</p>;
  }

  const v = detail.vehicle;

  return (
    <div className="space-y-8">
      <div>
        <Link
          href={`/dashboard/customers/${v.customer_id}`}
          className="text-sm text-[var(--muted)] hover:text-[var(--accent)]"
        >
          ← Back to customer
        </Link>
        <h1 className="page-title mt-2">
          {v.year} {v.make} {v.model}
        </h1>
        <p className="font-mono text-sm text-[var(--muted)]">{v.vin}</p>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <section className="grid grid-cols-2 gap-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 lg:grid-cols-4">
        <Stat label="Plate" value={v.license_plate ?? "—"} />
        <Stat label="Mileage" value={v.mileage.toLocaleString()} />
        <Stat label="Year" value={String(v.year)} />
        <Stat label="Make / Model" value={`${v.make} ${v.model}`} />
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">Repair history</h2>
        <div className="space-y-3">
          {detail.repair_history.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No repair history yet</p>
          ) : (
            detail.repair_history.map((h) => (
              <div key={h.id} className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-medium">{h.service_type}</p>
                  <p className="text-sm font-semibold">${Number(h.cost).toFixed(2)}</p>
                </div>
                <p className="mt-2 text-sm text-[var(--muted)]">{h.description}</p>
                {h.recommendation && (
                  <p className="mt-2 text-sm">
                    <span className="font-medium">Recommendation:</span> {h.recommendation}
                  </p>
                )}
                {h.created_at && (
                  <p className="mt-2 text-xs text-[var(--muted)]">
                    {new Date(h.created_at).toLocaleString()}
                  </p>
                )}
              </div>
            ))
          )}
        </div>

        <form
          onSubmit={onAddHistory}
          className="grid gap-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:grid-cols-2"
        >
          <Field label="Service type" value={serviceType} onChange={setServiceType} required />
          <Field label="Cost" value={cost} onChange={setCost} required />
          <label className="block space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Description</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
            />
          </label>
          <label className="block space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Recommendation</span>
            <textarea
              value={recommendation}
              onChange={(e) => setRecommendation(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
            />
          </label>
          <div className="sm:col-span-2">
            <button type="submit" className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white">
              Add repair history
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-[0.08em] text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-sm font-medium">{value}</p>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      <input
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
      />
    </label>
  );
}
