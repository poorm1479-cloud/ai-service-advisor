"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { deleteVehicle, getVehicleDetail, VehicleDetail } from "@/lib/crm";
import { useAuth } from "@/lib/auth";

export default function VehicleDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const vehicleId = params.id;
  const { session, loading: authLoading } = useAuth();
  const [detail, setDetail] = useState<VehicleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);

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

  async function onDelete() {
    if (!detail) return;
    const v = detail.vehicle;
    if (
      !window.confirm(
        `Delete ${v.year} ${v.make} ${v.model}? Repair history for this vehicle will also be removed.`,
      )
    ) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      await deleteVehicle(vehicleId);
      router.push(
        v.customer_id ? `/dashboard/customers/${v.customer_id}` : "/dashboard/customers",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete vehicle");
      setDeleting(false);
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
      <div className="flex flex-wrap items-end justify-between gap-3">
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
        <button
          type="button"
          onClick={() => void onDelete()}
          disabled={deleting}
          className="rounded-md border border-red-200 px-4 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-60"
        >
          {deleting ? "Deleting…" : "Delete vehicle"}
        </button>
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
