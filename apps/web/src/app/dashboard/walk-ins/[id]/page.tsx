"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  attachRepairToWalkIn,
  attachVehicleToWalkIn,
  convertWalkIn,
  getWalkIn,
  WalkInDetail,
} from "@/lib/walkin";
import { useAuth } from "@/lib/auth";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { listShopServices, ShopService } from "@/lib/shopSetup";

export default function WalkInDetailPage() {
  const params = useParams<{ id: string }>();
  const visitId = params.id;
  const { session, loading: authLoading } = useAuth();
  const [detail, setDetail] = useState<WalkInDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [address, setAddress] = useState("");

  const [vin, setVin] = useState("");
  const [plate, setPlate] = useState("");
  const [year, setYear] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [mileage, setMileage] = useState("");

  const [services, setServices] = useState<ShopService[]>([]);
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [serviceType, setServiceType] = useState("");
  const [description, setDescription] = useState("");
  const [cost, setCost] = useState("0");
  const [recommendation, setRecommendation] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await getWalkIn(visitId);
      setDetail(next);
      // Prefill attach/replace form from the vehicle already on this visit
      setVin(next.vehicle.vin);
      setPlate(next.vehicle.license_plate ?? "");
      setYear(String(next.vehicle.year));
      setMake(next.vehicle.make);
      setModel(next.vehicle.model);
      setMileage(String(next.vehicle.mileage));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load walk-in");
    } finally {
      setLoading(false);
    }
  }, [visitId]);

  useEffect(() => {
    if (!authLoading && session && visitId) {
      void load();
    }
  }, [authLoading, session, visitId, load]);

  useEffect(() => {
    if (authLoading || !session) return;
    void listShopServices(true)
      .then(setServices)
      .catch(() => setServices([]));
  }, [authLoading, session]);

  function onSelectService(id: string) {
    setSelectedServiceId(id);
    const svc = services.find((s) => s.id === id);
    if (!svc) return;
    setServiceType(svc.name);
    setCost(String(Number(svc.price)));
  }

  async function onConvert(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const next = await convertWalkIn(visitId, {
        name,
        phone: phone || undefined,
        email: email || undefined,
        address: address || undefined,
      });
      setDetail(next);
      setName("");
      setPhone("");
      setEmail("");
      setAddress("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Convert failed");
    }
  }

      async function onAttachVehicle(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const next = await attachVehicleToWalkIn(visitId, {
        vin,
        license_plate: plate || undefined,
        year: Number(year),
        make,
        model,
        mileage: Number(mileage),
      });
      setDetail(next);
      setVin(next.vehicle.vin);
      setPlate(next.vehicle.license_plate ?? "");
      setYear(String(next.vehicle.year));
      setMake(next.vehicle.make);
      setModel(next.vehicle.model);
      setMileage(String(next.vehicle.mileage));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attach vehicle failed");
    }
  }

  async function onAttachRepair(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const next = await attachRepairToWalkIn(visitId, {
        service_type: serviceType,
        description,
        cost: Number(cost),
        recommendation: recommendation || undefined,
      });
      setDetail(next);
      setSelectedServiceId("");
      setServiceType("");
      setDescription("");
      setCost("0");
      setRecommendation("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Attach repair failed");
    }
  }

  if (loading) {
    return <p className="text-sm text-[var(--muted)]">Loading walk-in…</p>;
  }

  if (!detail) {
    return <p className="text-sm text-red-700">{error ?? "Walk-in not found"}</p>;
  }

  const { visit, vehicle, customer, repair_history } = detail;
  const serviceRequests = visit.complaint
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <div className="space-y-8">
      <div>
        <Link href="/dashboard/walk-ins" className="text-sm text-[var(--muted)] hover:text-[var(--accent)]">
          ← Walk-ins
        </Link>
        <h1 className="page-title mt-2">Walk-in visit</h1>
        <p className="text-sm capitalize text-[var(--muted)]">
          Status: {visit.status}
          {visit.arrived_at ? ` · Arrived ${new Date(visit.arrived_at).toLocaleString()}` : ""}
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
        <h2 className="text-sm font-semibold">Service Request</h2>
        {serviceRequests.length <= 1 ? (
          <p className="mt-2 text-sm">{visit.complaint}</p>
        ) : (
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {serviceRequests.map((item, i) => (
              <li key={`${i}-${item}`}>{item}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold">Vehicle</h2>
          <Link href={`/dashboard/vehicles/${vehicle.id}`} className="text-sm text-[var(--accent)]">
            Open vehicle page
          </Link>
        </div>
        <p className="mt-2 text-sm">
          {vehicle.year} {vehicle.make} {vehicle.model}
        </p>
        <p className="font-mono text-xs text-[var(--muted)]">{vehicle.vin}</p>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Plate {vehicle.license_plate ?? "—"} · {vehicle.mileage.toLocaleString()} mi
        </p>
      </section>

      <section className="space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
        <h2 className="text-sm font-semibold">Customer Match</h2>
        {customer ? (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-emerald-800">
              Existing customer found
            </p>
            <Link
              href={`/dashboard/customers/${customer.id}`}
              className="mt-1 inline-block font-medium text-[var(--accent)]"
            >
              {customer.name}
            </Link>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {customer.phone ?? "No phone"} · {customer.email ?? "No email"}
            </p>
          </div>
        ) : (
          <form onSubmit={onConvert} className="grid gap-3 sm:grid-cols-2">
            <p className="sm:col-span-2 text-sm text-[var(--muted)]">
              Unknown walk-in — this visit uses a guest customer. Add real details when you have
              them. Name is required to save.
            </p>
            <Field label="Name" value={name} onChange={setName} />
            <Field
              label="Phone (optional)"
              type="tel"
              value={phone}
              onChange={(v) => setPhone(formatPhoneInput(v))}
              placeholder={PHONE_PLACEHOLDER}
            />
            <Field label="Email (optional)" type="email" value={email} onChange={setEmail} />
            <Field label="Address (optional)" value={address} onChange={setAddress} />
            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={!name.trim()}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                Save customer
              </button>
            </div>
          </form>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">Attach / replace vehicle</h2>
        <form
          onSubmit={onAttachVehicle}
          className="grid gap-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:grid-cols-3"
        >
          <p className="text-sm text-[var(--muted)] sm:col-span-3">
            Prefills from the vehicle already on this visit. Edit only if you need to correct or
            replace it.
          </p>
          <Field label="VIN" value={vin} onChange={setVin} required />
          <Field label="License plate" value={plate} onChange={setPlate} />
          <Field label="Year" value={year} onChange={setYear} required />
          <Field label="Make" value={make} onChange={setMake} required />
          <Field label="Model" value={model} onChange={setModel} required />
          <Field label="Mileage" value={mileage} onChange={setMileage} required />
          <div className="sm:col-span-3">
            <button type="submit" className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white">
              Update vehicle
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <h2 className="text-sm font-semibold">Repair history</h2>
        <div className="space-y-3">
          {repair_history.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No repair history attached yet</p>
          ) : (
            repair_history.map((h) => (
              <div key={h.id} className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
                <div className="flex justify-between gap-2">
                  <p className="font-medium">{h.service_type}</p>
                  <p className="text-sm font-semibold">${Number(h.cost).toFixed(2)}</p>
                </div>
                <p className="mt-2 text-sm text-[var(--muted)]">{h.description}</p>
              </div>
            ))
          )}
        </div>
        <form
          onSubmit={onAttachRepair}
          className="grid gap-3 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 sm:grid-cols-2"
        >
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Service type</span>
            <select
              required
              value={selectedServiceId}
              onChange={(e) => onSelectService(e.target.value)}
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
            >
              <option value="" disabled>
                {services.length === 0 ? "No active services — add in Service Catalog" : "Select a service…"}
              </option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} — ${Number(s.price).toFixed(2)}
                </option>
              ))}
            </select>
          </label>
          <Field label="Cost" value={cost} onChange={setCost} required />
          <label className="block space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Description</span>
            <textarea
              value={description}
              rows={3}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
            />
          </label>
          <label className="block space-y-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Recommendation</span>
            <textarea
              value={recommendation}
              rows={2}
              onChange={(e) => setRecommendation(e.target.value)}
              className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
            />
          </label>
          <div className="sm:col-span-2">
            <button type="submit" className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white">
              Attach repair history
            </button>
          </div>
        </form>
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
