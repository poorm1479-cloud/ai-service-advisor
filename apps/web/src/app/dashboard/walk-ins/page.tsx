"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import {
  FormEvent,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  convertWalkIn,
  createWalkIn,
  listWalkIns,
  vehicleMatchAssist,
  vinAssist,
  WalkInVisit,
} from "@/lib/walkin";
import {
  Customer,
  getCustomerDetail,
  getVehicleDetail,
  RepairHistory,
  Vehicle,
} from "@/lib/crm";
import { useAuth } from "@/lib/auth";
import { listShopServices, ShopService } from "@/lib/shopSetup";

const VinInput = dynamic(
  () => import("@/components/VinInput").then((m) => ({ default: m.VinInput })),
  {
    ssr: false,
    loading: () => (
      <div className="h-10 animate-pulse rounded-md border border-[var(--line)] bg-[var(--background)]/60" />
    ),
  },
);

const VIN_ALPHABET = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789";

type EntryMode = "vin" | "manual";
type PageView = "intake" | "todays";
/** URL `?view=` — keeps No VIN / Today's selection across menu navigation. */
type WalkInView = "vin" | "manual" | "todays";

function parseWalkInView(value: string | null): WalkInView {
  if (value === "manual" || value === "todays" || value === "vin") return value;
  return "vin";
}

type MatchContext = {
  vehicle: Vehicle;
  customer: Customer | null;
  repairs: RepairHistory[];
};

/** Temporary VIN when plate/scan unavailable — valid charset for existing API. */
function makeTempVin(): string {
  const stamp = Date.now().toString(36).toUpperCase().replace(/[IOQ]/g, "");
  let out = `TMP${stamp}`;
  while (out.length < 17) {
    out += VIN_ALPHABET[Math.floor(Math.random() * VIN_ALPHABET.length)];
  }
  return out.slice(0, 17);
}

function buildAiRecommendations(complaint: string, repairs: RepairHistory[]): string[] {
  const fromHistory = repairs
    .map((r) => r.recommendation?.trim())
    .filter((r): r is string => Boolean(r));
  const unique = [...new Set(fromHistory)].slice(0, 3);

  const tips: string[] = [...unique];
  const c = complaint.toLowerCase();
  if (/brake/.test(c)) tips.push("Inspect pads, rotors, and fluid — common follow-up after brake noise.");
  if (/check engine|cel|diagnostic/.test(c)) tips.push("Scan codes first; compare to prior diagnostic visits.");
  if (/oil|maintenance/.test(c)) tips.push("Confirm interval vs last oil service mileage.");
  if (/battery|no-?start/.test(c)) tips.push("Test battery/alternator before parts — note prior electrical work.");
  if (/tire|vibration/.test(c)) tips.push("Check tire wear pattern, balance, and alignment history.");
  if (/ac|a\/c|cooling/.test(c)) tips.push("Verify blower and pressures; review past AC repairs.");
  if (/noise|engine/.test(c) && !/brake/.test(c)) tips.push("Ask when noise occurs (cold/hot/accel) before road test.");

  if (tips.length === 0 && repairs.length > 0) {
    tips.push("Review prior services below before quoting — returning vehicle.");
  }
  if (tips.length === 0) {
    tips.push("New to shop or no history yet — confirm concern and mileage, then inspect.");
  }
  return [...new Set(tips)].slice(0, 4);
}

function WalkInsContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { session, loading: authLoading } = useAuth();
  const [visits, setVisits] = useState<WalkInVisit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [services, setServices] = useState<ShopService[]>([]);

  const walkInView = parseWalkInView(searchParams.get("view"));
  const pageView: PageView = walkInView === "todays" ? "todays" : "intake";
  const entryMode: EntryMode = walkInView === "manual" ? "manual" : "vin";

  const [vin, setVin] = useState("");
  const [plate, setPlate] = useState("");
  const [year, setYear] = useState("");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [mileage, setMileage] = useState("");
  const [complaints, setComplaints] = useState<string[]>([""]);
  // Empty until mount — server/client timezone & clock would otherwise mismatch.
  const [arrivedAt, setArrivedAt] = useState("");
  useEffect(() => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    setArrivedAt(now.toISOString().slice(0, 16));
  }, []);

  const [saving, setSaving] = useState(false);
  const [vinStatus, setVinStatus] = useState<string | null>(null);
  const [vinLooking, setVinLooking] = useState(false);
  const [autoFilled, setAutoFilled] = useState(false);
  const [match, setMatch] = useState<MatchContext | null>(null);
  const [matchLoading, setMatchLoading] = useState(false);
  const assistSeq = useRef(0);

  const complaintText = useMemo(
    () => complaints.map((c) => c.trim()).filter(Boolean).join("\n"),
    [complaints],
  );

  const recommendations = useMemo(
    () => (match ? buildAiRecommendations(complaintText, match.repairs) : []),
    [match, complaintText],
  );

  function togglePreset(preset: string) {
    setComplaints((prev) => {
      const trimmed = prev.map((c) => c.trim());
      const idx = trimmed.indexOf(preset);
      if (idx >= 0) {
        const next = prev.filter((_, i) => i !== idx);
        return next.length > 0 ? next : [""];
      }
      // Fill first empty row, otherwise append
      const emptyIdx = prev.findIndex((c) => !c.trim());
      if (emptyIdx >= 0) {
        const next = [...prev];
        next[emptyIdx] = preset;
        return next;
      }
      return [...prev, preset];
    });
  }

  function updateComplaint(index: number, value: string) {
    setComplaints((prev) => prev.map((c, i) => (i === index ? value : c)));
  }

  function addComplaint() {
    setComplaints((prev) => [...prev, ""]);
  }

  function removeComplaint(index: number) {
    setComplaints((prev) => {
      const next = prev.filter((_, i) => i !== index);
      return next.length > 0 ? next : [""];
    });
  }

  async function loadTodays() {
    setLoading(true);
    setError(null);
    try {
      const start = new Date();
      start.setHours(0, 0, 0, 0);
      setVisits(await listWalkIns(undefined, start.toISOString()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load walk-ins");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && session) {
      // Intake only needs services — defer walk-in list until Today's tab
      void listShopServices(true)
        .then(setServices)
        .catch(() => setServices([]));
    }
  }, [authLoading, session]);

  useEffect(() => {
    if (!authLoading && session && walkInView === "todays") {
      void loadTodays();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refresh when opening Today's view
  }, [authLoading, session, walkInView]);

  async function hydrateMatch(v: Vehicle, seq: number) {
    let customer: Customer | null = null;
    let repairs: RepairHistory[] = [];
    try {
      const [vehicleDetail, customerDetail] = await Promise.all([
        getVehicleDetail(v.id),
        v.customer_id ? getCustomerDetail(v.customer_id) : Promise.resolve(null),
      ]);
      if (seq !== assistSeq.current) return;
      repairs = vehicleDetail.repair_history;
      customer = customerDetail?.customer ?? null;
    } catch {
      // Match panel is best-effort; intake can continue
    }
    if (seq !== assistSeq.current) return;
    setMatch({ vehicle: v, customer, repairs });
  }

  useEffect(() => {
    if (entryMode !== "vin") return;

    const cleaned = vin.replace(/[\s-]/g, "").toUpperCase();
    if (cleaned.length !== 17) {
      setVinStatus(null);
      setVinLooking(false);
      setMatch(null);
      return;
    }

    const seq = ++assistSeq.current;
    const timer = window.setTimeout(() => {
      void (async () => {
        setVinLooking(true);
        setMatchLoading(true);
        try {
          const assist = await vinAssist(cleaned);
          if (seq !== assistSeq.current) return;

          if (assist.existing) {
            const v = assist.existing;
            setVin(v.vin);
            setPlate(v.license_plate ?? "");
            setYear(String(v.year));
            setMake(v.make);
            setModel(v.model);
            setMileage(String(v.mileage));
            setAutoFilled(true);
            await hydrateMatch(v, seq);
          } else if (assist.decoded) {
            const d = assist.decoded;
            setVin(d.vin);
            setYear(String(d.year));
            setMake(d.make);
            setModel(d.model);
            setAutoFilled(true);
            setMatch(null);
          } else {
            setAutoFilled(false);
            setMatch(null);
          }
          setVinStatus(assist.message);
        } catch (err) {
          if (seq !== assistSeq.current) return;
          setAutoFilled(false);
          setMatch(null);
          setVinStatus(err instanceof Error ? err.message : "VIN lookup failed");
        } finally {
          if (seq === assistSeq.current) {
            setVinLooking(false);
            setMatchLoading(false);
          }
        }
      })();
    }, 350);

    return () => window.clearTimeout(timer);
  }, [vin, entryMode]);

  useEffect(() => {
    if (entryMode !== "manual") return;

    const cleanedPlate = plate.replace(/[\s-]/g, "").toUpperCase();
    const yearNum = Number(year);
    const hasPlate = cleanedPlate.length >= 3;
    const hasYmm =
      Number.isFinite(yearNum) &&
      year.trim().length === 4 &&
      make.trim().length >= 2 &&
      model.trim().length >= 1;

    if (!hasPlate && !hasYmm) {
      setVinStatus(null);
      setVinLooking(false);
      setMatchLoading(false);
      setMatch(null);
      return;
    }

    const seq = ++assistSeq.current;
    const timer = window.setTimeout(() => {
      void (async () => {
        setVinLooking(true);
        setMatchLoading(true);
        try {
          const assist = await vehicleMatchAssist({
            license_plate: hasPlate ? cleanedPlate : undefined,
            year: hasYmm ? yearNum : undefined,
            make: hasYmm ? make.trim() : undefined,
            model: hasYmm ? model.trim() : undefined,
          });
          if (seq !== assistSeq.current) return;

          if (assist.existing) {
            const v = assist.existing;
            setVin(v.vin);
            if (assist.match_type === "license_plate") {
              setYear(String(v.year));
              setMake(v.make);
              setModel(v.model);
              setMileage((prev) => prev || String(v.mileage));
              setAutoFilled(true);
            } else if (!cleanedPlate && v.license_plate) {
              setPlate(v.license_plate);
            }
            await hydrateMatch(v, seq);
          } else {
            setVin("");
            setAutoFilled(false);
            setMatch(null);
          }
          setVinStatus(assist.message);
        } catch (err) {
          if (seq !== assistSeq.current) return;
          setVin("");
          setAutoFilled(false);
          setMatch(null);
          setVinStatus(err instanceof Error ? err.message : "Vehicle lookup failed");
        } finally {
          if (seq === assistSeq.current) {
            setVinLooking(false);
            setMatchLoading(false);
          }
        }
      })();
    }, 400);

    return () => window.clearTimeout(timer);
  }, [entryMode, plate, year, make, model]);

  const selectView = useCallback(
    (next: WalkInView) => {
      if (next === "vin" || next === "manual") {
        setVinStatus(null);
        setMatch(null);
        setAutoFilled(false);
        if (next === "manual") {
          assistSeq.current += 1;
          setVin("");
          setVinLooking(false);
          setMatchLoading(false);
        }
      }
      const params = new URLSearchParams(searchParams.toString());
      if (next === "vin") {
        params.delete("view");
      } else {
        params.set("view", next);
      }
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const cleanedVin = vin.replace(/[\s-]/g, "").toUpperCase();
      const matchedVin = match?.vehicle.vin.replace(/[\s-]/g, "").toUpperCase() ?? "";
      const submitVin =
        matchedVin.length === 17
          ? matchedVin
          : cleanedVin.length === 17
            ? cleanedVin
            : entryMode === "manual"
              ? makeTempVin()
              : cleanedVin;

      if (submitVin.length !== 17) {
        throw new Error("Enter a 17-character VIN, or switch to manual vehicle entry");
      }

      if (services.length === 0) {
        throw new Error("Add at least one active service in Service Catalog first");
      }

      if (!complaintText) {
        throw new Error("Select at least one service request");
      }

      let detail = await createWalkIn({
        vin: submitVin,
        license_plate: plate || undefined,
        year: Number(year),
        make,
        model,
        mileage: Number(mileage || 0),
        complaint: complaintText,
        arrived_at: new Date(arrivedAt || Date.now()).toISOString(),
      });

      // Link a guest customer so Customers + dashboard New Customers update
      if (!detail.customer) {
        const vehicleLabel = [year, make, model].filter(Boolean).join(" ").trim();
        detail = await convertWalkIn(detail.visit.id, {
          name: vehicleLabel
            ? `Unknown walk-in · ${vehicleLabel}`
            : "Unknown walk-in",
        });
      }

      // Schedule from the visit page: Start now or Appointment
      router.push(`/dashboard/walk-ins/${detail.visit.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start service visit");
      setSaving(false);
    }
  }

  const matchedExisting = Boolean(match?.customer);
  const customerMatchMode: "existing" | "unknown" = matchedExisting
    ? "existing"
    : "unknown";

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="shrink-0">
        <h1 className="page-title">Walk-ins</h1>
      </div>

      {error && (
        <p className="shrink-0 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
        <div className="flex shrink-0 flex-wrap gap-2">
          <ModeChip
            active={pageView === "intake" && entryMode === "vin"}
            onClick={() => selectView("vin")}
            label="Scan / enter VIN"
          />
          <ModeChip
            active={pageView === "intake" && entryMode === "manual"}
            onClick={() => selectView("manual")}
            label="No VIN — enter vehicle"
          />
          <ModeChip
            active={pageView === "todays"}
            onClick={() => selectView("todays")}
            label="Today's walk-ins"
          />
        </div>

        {pageView === "todays" ? (
          <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
            <h2 className="mb-2 shrink-0 text-sm font-semibold">Today&apos;s walk-ins</h2>
            <div className="table-scroll asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain">
              <table>
                <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                  <tr>
                    <th className="px-3 py-2">Arrived</th>
                    <th className="px-3 py-2">Service Request</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Customer</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={4} className="px-3 py-6 text-[var(--muted)]">
                        Loading…
                      </td>
                    </tr>
                  ) : visits.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="px-3 py-6 text-[var(--muted)]">
                        No walk-ins yet
                      </td>
                    </tr>
                  ) : (
                    visits.map((v) => (
                      <tr
                        key={v.id}
                        className="border-t border-[var(--line)] hover:bg-[var(--accent-soft)]/40"
                      >
                        <td className="px-3 py-2 text-xs text-[var(--muted)]">
                          {v.arrived_at ? new Date(v.arrived_at).toLocaleString() : "—"}
                        </td>
                        <td className="px-3 py-2">
                          <Link
                            href={`/dashboard/walk-ins/${v.id}`}
                            className="text-sm font-medium text-[var(--accent)]"
                          >
                            <span className="whitespace-pre-line">
                              {v.complaint.split("\n").filter(Boolean).join(" · ") || v.complaint}
                            </span>
                          </Link>
                        </td>
                        <td className="px-3 py-2 capitalize text-xs text-[var(--muted)]">{v.status}</td>
                        <td className="px-3 py-2 text-xs text-[var(--muted)]">
                          {v.customer_id ? "Linked" : "Unknown"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
      <form
        onSubmit={onCreate}
        className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4"
      >

        {entryMode === "vin" ? (
          <VinInput
            value={vin}
            onChange={setVin}
            status={vinStatus}
            looking={vinLooking}
            required
          />
        ) : (
          <div className="space-y-1">
            <p className="text-sm text-[var(--muted)]">
              Enter plate and/or year, make, model. Matching customers are linked automatically; a
              temporary VIN is used only when no vehicle is found.
            </p>
            {(vinLooking || vinStatus) && (
              <p className="text-xs text-[var(--muted)]">
                {vinLooking ? "Looking up vehicle…" : vinStatus}
              </p>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Field
            label={`Year${autoFilled ? " (auto)" : ""}`}
            value={year}
            onChange={setYear}
            required
            placeholder={entryMode === "vin" ? "Auto from VIN" : "e.g. 2018"}
          />
          <Field
            label={`Make${autoFilled ? " (auto)" : ""}`}
            value={make}
            onChange={setMake}
            required
            placeholder={entryMode === "vin" ? "Auto from VIN" : "e.g. Toyota"}
          />
          <Field
            label={`Model${autoFilled ? " (auto)" : ""}`}
            value={model}
            onChange={setModel}
            required
            placeholder={entryMode === "vin" ? "Auto from VIN" : "e.g. Camry"}
          />
          <Field label="License plate" value={plate} onChange={setPlate} placeholder="Optional" />
          <Field
            label="Mileage"
            value={mileage}
            onChange={setMileage}
            required
            placeholder="Current odometer"
          />
          <Field
            label="Arrival time"
            type="datetime-local"
            value={arrivedAt}
            onChange={setArrivedAt}
            required
          />
        </div>

        {/* Customer Match — never requires name/phone; anonymous walk-ins allowed */}
        <section className="rounded-lg border border-dashed border-[var(--line)] bg-[var(--background)]/60 p-3">
          <h2 className="text-sm font-semibold">Customer Match</h2>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Name and phone are never required. Unknown walk-ins still create a guest customer.
          </p>

          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <MatchOption
              active={customerMatchMode === "existing"}
              disabled={!matchedExisting}
              label="Existing customer found"
              description={
                match?.customer
                  ? match.customer.name
                  : "Shown when plate or vehicle details match a customer"
              }
              onClick={() => undefined}
            />
            <MatchOption
              active={customerMatchMode === "unknown"}
              disabled={matchedExisting}
              label="Unknown walk-in"
              description="Creates a guest customer for this visit"
              onClick={() => undefined}
            />
          </div>

          {match?.customer && (
            <p className="mt-3 text-sm">
              Linked:{" "}
              <Link
                href={`/dashboard/customers/${match.customer.id}`}
                className="font-medium text-[var(--accent)]"
              >
                {match.customer.name}
              </Link>
              {match.customer.phone ? (
                <span className="text-[var(--muted)]"> · {match.customer.phone}</span>
              ) : null}
            </p>
          )}
        </section>

        {/* After VIN lookup: vehicle history, previous repairs, AI recommendation */}
        {(matchLoading || match) && (
          <section className="space-y-3 rounded-lg border border-[var(--line)] bg-[var(--background)]/60 p-3">
            <h2 className="text-sm font-semibold">Vehicle match</h2>
            {matchLoading && !match ? (
              <p className="text-sm text-[var(--muted)]">Loading vehicle history…</p>
            ) : match ? (
              <div className="grid gap-3 lg:grid-cols-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                    Vehicle history
                  </p>
                  <ul className="mt-1 space-y-1 text-sm">
                    <li>
                      {match.vehicle.year} {match.vehicle.make} {match.vehicle.model}
                    </li>
                    <li className="font-mono text-xs text-[var(--muted)]">{match.vehicle.vin}</li>
                    <li className="text-[var(--muted)]">
                      Plate {match.vehicle.license_plate ?? "—"} ·{" "}
                      {match.vehicle.mileage.toLocaleString()} mi on file
                    </li>
                    {match.customer ? (
                      <li className="text-[var(--muted)]">
                        Owner: {match.customer.name}
                        {match.customer.phone ? ` · ${match.customer.phone}` : ""}
                      </li>
                    ) : (
                      <li className="text-[var(--muted)]">No customer linked to this vehicle</li>
                    )}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                    Previous repairs
                  </p>
                  {match.repairs.length === 0 ? (
                    <p className="mt-1 text-sm text-[var(--muted)]">No prior repairs</p>
                  ) : (
                    <ul className="mt-1 max-h-36 space-y-2 overflow-y-auto text-sm">
                      {match.repairs.slice(0, 5).map((r) => (
                        <li key={r.id}>
                          <span className="font-medium">{r.service_type}</span>
                          <span className="text-[var(--muted)]">
                            {" "}
                            · ${Number(r.cost).toFixed(0)}
                            {r.created_at
                              ? ` · ${new Date(r.created_at).toLocaleDateString()}`
                              : ""}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
                    AI recommendation
                  </p>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-sm text-[var(--muted)]">
                    {recommendations.map((tip) => (
                      <li key={tip}>{tip}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : null}
          </section>
        )}

        <div className="space-y-2">
          <span className="text-sm font-medium">Service Request</span>
          <p className="text-xs text-[var(--muted)]">
            Choose from your Service Catalog. Tap a service to add or remove it.
          </p>
          {services.length === 0 ? (
            <p className="rounded-md border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-sm text-[var(--muted)]">
              No active services yet.{" "}
              <Link href="/dashboard/services" className="font-medium text-[var(--accent)] hover:underline">
                Add services in Service Catalog
              </Link>
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {services.map((svc) => {
                const selected = complaints.some((c) => c.trim() === svc.name);
                return (
                  <button
                    key={svc.id}
                    type="button"
                    onClick={() => togglePreset(svc.name)}
                    className={`rounded-md border px-2.5 py-1.5 text-xs ${
                      selected
                        ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                        : "border-[var(--line)] text-[var(--muted)] hover:border-[var(--accent)]"
                    }`}
                  >
                    {svc.name}
                  </button>
                );
              })}
            </div>
          )}
          <div className="space-y-2">
            {complaints.map((item, index) => (
              <div key={index} className="flex gap-2">
                <select
                  value={item}
                  required={index === 0 || Boolean(item.trim())}
                  onChange={(e) => updateComplaint(index, e.target.value)}
                  className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                >
                  <option value="" disabled>
                    {services.length === 0
                      ? "No active services — add in Service Catalog"
                      : index === 0
                        ? "Select a service…"
                        : "Additional service…"}
                  </option>
                  {services.map((svc) => (
                    <option key={svc.id} value={svc.name}>
                      {svc.name}
                      {svc.price != null ? ` — $${Number(svc.price).toFixed(2)}` : ""}
                    </option>
                  ))}
                </select>
                {complaints.length > 1 ? (
                  <button
                    type="button"
                    onClick={() => removeComplaint(index)}
                    className="shrink-0 rounded-md border border-[var(--line)] px-2.5 text-sm text-[var(--muted)] hover:border-red-300 hover:text-red-700"
                    aria-label={`Remove service request ${index + 1}`}
                  >
                    Remove
                  </button>
                ) : null}
              </div>
            ))}
          </div>
          <button
            type="button"
            onClick={addComplaint}
            disabled={services.length === 0}
            className="text-sm font-medium text-[var(--accent)] hover:underline disabled:opacity-50"
          >
            + Add another request
          </button>
        </div>

        <button
          type="submit"
          disabled={saving || vinLooking || services.length === 0}
          className="rounded-md bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white disabled:opacity-60"
        >
          {saving ? "Starting…" : "Start Service"}
        </button>
      </form>
        )}
      </div>
    </div>
  );
}

export default function WalkInsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-[var(--muted)]">Loading walk-ins…</p>}>
      <WalkInsContent />
    </Suspense>
  );
}

function ModeChip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md border px-3 py-1.5 text-sm ${
        active
          ? "border-[var(--accent)] bg-[var(--accent-soft)] font-medium text-[var(--accent)]"
          : "border-[var(--line)] text-[var(--muted)] hover:border-[var(--accent)]"
      }`}
    >
      {label}
    </button>
  );
}

function MatchOption({
  active,
  disabled,
  label,
  description,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-md border px-3 py-2 text-left transition ${
        active
          ? "border-[var(--accent)] bg-[var(--accent-soft)]"
          : disabled
            ? "cursor-not-allowed border-[var(--line)] opacity-50"
            : "border-[var(--line)] hover:border-[var(--accent)]"
      }`}
    >
      <span
        className={`block text-sm font-medium ${
          active ? "text-[var(--accent)]" : "text-[var(--foreground)]"
        }`}
      >
        {label}
      </span>
      <span className="mt-0.5 block text-xs text-[var(--muted)]">{description}</span>
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
        placeholder={placeholder}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
      />
    </label>
  );
}
