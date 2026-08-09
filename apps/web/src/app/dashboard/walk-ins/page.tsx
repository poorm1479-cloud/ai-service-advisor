"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import {
  FormEvent,
  ReactNode,
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

  const waitingCount = visits.filter((v) => v.status === "open").length;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Walk-ins</h1>
        </div>
        {pageView === "todays" && !loading ? (
          <span className="rounded-full bg-[var(--background)] px-3 py-1 text-[11px] font-semibold tabular-nums text-[var(--muted)] ring-1 ring-[var(--line)]">
            {visits.length} today
            {waitingCount > 0 ? ` · ${waitingCount} waiting` : ""}
          </span>
        ) : null}
      </div>

      {error && (
        <p
          className="shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden">
        <div
          className="surface-panel flex shrink-0 gap-1 p-1.5"
          role="tablist"
          aria-label="Walk-in mode"
        >
          <ModeChip
            active={pageView === "intake" && entryMode === "vin"}
            onClick={() => selectView("vin")}
            label="Scan VIN"
            hint="Barcode or type"
            icon={<IconScanVin />}
          />
          <ModeChip
            active={pageView === "intake" && entryMode === "manual"}
            onClick={() => selectView("manual")}
            label="No VIN"
            hint="Plate / YMM"
            icon={<IconNoVin />}
          />
          <ModeChip
            active={pageView === "todays"}
            onClick={() => selectView("todays")}
            label="Today"
            hint="Queue"
            icon={<IconQueue />}
          />
        </div>

        {pageView === "todays" ? (
          <section className="surface-panel flex min-h-0 flex-1 flex-col overflow-hidden">
            <header className="flex shrink-0 items-center gap-2.5 border-b border-[var(--line)] px-4 py-3">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                <IconQueue />
              </span>
              <p className="text-sm font-semibold tracking-tight">List</p>
            </header>

            <div className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain">
              {loading ? (
                <div className="space-y-3 px-4 py-5">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="flex animate-pulse gap-3 rounded-xl bg-[var(--background)]/70 p-3">
                      <div className="h-10 w-10 rounded-full bg-[var(--panel)]" />
                      <div className="min-w-0 flex-1 space-y-2 py-1">
                        <div className="h-3 w-2/3 rounded bg-[var(--panel)]" />
                        <div className="h-2.5 w-1/2 rounded bg-[var(--panel)]" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : visits.length === 0 ? (
                <div className="flex flex-col items-center px-6 py-16 text-center">
                  <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                    <IconQueue />
                  </span>
                  <p className="font-display text-lg font-semibold tracking-tight">No walk-ins yet</p>
                  <p className="mt-1 max-w-xs text-sm text-[var(--muted)]">
                    Check-ins from today will appear here as a live queue.
                  </p>
                  <button
                    type="button"
                    onClick={() => selectView("vin")}
                    className="btn-primary mt-5 px-4 py-2 text-xs"
                  >
                    Start first check-in
                  </button>
                </div>
              ) : (
                <ul className="divide-y divide-[var(--line)]">
                  {visits.map((v) => {
                    const servicesLine =
                      v.complaint.split("\n").filter(Boolean).join(" · ") || v.complaint;
                    return (
                      <li key={v.id}>
                        <Link
                          href={`/dashboard/walk-ins/${v.id}`}
                          className="group flex items-start gap-3 px-4 py-3.5 transition hover:bg-[var(--accent-soft)]/35"
                        >
                          <span
                            className="mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-xs font-semibold tracking-wide text-[var(--muted)] ring-1 ring-[var(--line)] group-hover:bg-[var(--accent)] group-hover:text-white group-hover:ring-[var(--accent)]"
                            aria-hidden="true"
                          >
                            {visitInitials(v.complaint, Boolean(v.customer_id))}
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="truncate text-sm font-semibold tracking-tight group-hover:text-[var(--accent)]">
                                {servicesLine}
                              </p>
                              <StatusPill status={v.status} />
                            </div>
                            <p className="mt-1 text-xs text-[var(--muted)]">
                              {v.customer_id ? "Customer linked" : "Unknown walk-in"}
                              {v.arrived_at
                                ? ` · Arrived ${new Date(v.arrived_at).toLocaleString()}`
                                : ""}
                            </p>
                          </div>
                          <span className="mt-2 shrink-0 text-[var(--muted)] opacity-0 transition group-hover:opacity-100">
                            →
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </section>
        ) : (
          <form
            onSubmit={onCreate}
            className="surface-panel flex min-h-0 flex-1 flex-col overflow-hidden"
          >
            <div className="asa-scroll min-h-0 flex-1 space-y-5 overflow-y-auto overscroll-contain p-4 sm:p-5">
              <SectionHeader
                title="Vehicle"
                titleClassName="text-[var(--accent)]"
                description={
                  entryMode === "vin"
                    ? "Scan a barcode or enter the 17-character VIN to decode and match."
                    : "Use plate and/or year, make, model. A temporary VIN is assigned only when no vehicle matches."
                }
              />

              {entryMode === "vin" ? (
                <VinInput
                  value={vin}
                  onChange={setVin}
                  status={vinStatus}
                  looking={vinLooking}
                  required
                />
              ) : (vinLooking || vinStatus) ? (
                <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--background)]/50 px-3.5 py-3">
                  <p className="text-xs text-[var(--muted)]">
                    {vinLooking ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--accent)]" />
                        Looking up vehicle…
                      </span>
                    ) : (
                      vinStatus
                    )}
                  </p>
                </div>
              ) : null}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field
                  label={`Year${autoFilled ? " · auto" : ""}`}
                  value={year}
                  onChange={setYear}
                  required
                  placeholder={entryMode === "vin" ? "Auto from VIN" : "e.g. 2018"}
                />
                <Field
                  label={`Make${autoFilled ? " · auto" : ""}`}
                  value={make}
                  onChange={setMake}
                  required
                  placeholder={entryMode === "vin" ? "Auto from VIN" : "e.g. Toyota"}
                />
                <Field
                  label={`Model${autoFilled ? " · auto" : ""}`}
                  value={model}
                  onChange={setModel}
                  required
                  placeholder={entryMode === "vin" ? "Auto from VIN" : "e.g. Camry"}
                />
                <Field
                  label="License plate"
                  value={plate}
                  onChange={setPlate}
                  placeholder="Optional"
                />
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

              <section className="rounded-xl border border-[var(--line)] bg-[var(--background)]/55 p-4">
                <SectionHeader
                  title="Customer"
                  titleClassName="text-[var(--accent)]"
                  description="Name and phone are never required. Unknown walk-ins still create a guest customer."
                  compact
                />

                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <MatchOption
                    active={customerMatchMode === "existing"}
                    disabled={!matchedExisting}
                    label="Existing customer"
                    description={
                      match?.customer
                        ? match.customer.name
                        : "Appears when plate or vehicle details match"
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
                  <p className="mt-3 rounded-lg bg-[var(--panel)] px-3 py-2 text-sm ring-1 ring-[var(--line)]">
                    Linked:{" "}
                    <Link
                      href={`/dashboard/customer/${match.customer.id}`}
                      className="font-semibold text-[var(--accent)]"
                    >
                      {match.customer.name}
                    </Link>
                    {match.customer.phone ? (
                      <span className="text-[var(--muted)]"> · {match.customer.phone}</span>
                    ) : null}
                  </p>
                )}
              </section>

              {(matchLoading || match) && (
                <section className="rounded-xl border border-[var(--line)] bg-gradient-to-br from-[var(--panel)] to-[var(--background)] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
                  <SectionHeader
                    eyebrow="Intelligence"
                    title="Vehicle match"
                    description="History and suggestions for this check-in."
                    compact
                  />
                  {matchLoading && !match ? (
                    <p className="mt-3 text-sm text-[var(--muted)]">Loading vehicle history…</p>
                  ) : match ? (
                    <div className="mt-3 grid gap-3 lg:grid-cols-3">
                      <div className="rounded-xl bg-[var(--panel)] p-3 ring-1 ring-[var(--line)]">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                          Vehicle history
                        </p>
                        <ul className="mt-2 space-y-1 text-sm">
                          <li className="font-semibold tracking-tight">
                            {match.vehicle.year} {match.vehicle.make} {match.vehicle.model}
                          </li>
                          <li className="font-mono text-[11px] text-[var(--muted)]">
                            {match.vehicle.vin}
                          </li>
                          <li className="text-xs text-[var(--muted)]">
                            Plate {match.vehicle.license_plate ?? "—"} ·{" "}
                            {match.vehicle.mileage.toLocaleString()} mi on file
                          </li>
                          {match.customer ? (
                            <li className="text-xs text-[var(--muted)]">
                              Owner: {match.customer.name}
                              {match.customer.phone ? ` · ${match.customer.phone}` : ""}
                            </li>
                          ) : (
                            <li className="text-xs text-[var(--muted)]">
                              No customer linked to this vehicle
                            </li>
                          )}
                        </ul>
                      </div>
                      <div className="rounded-xl bg-[var(--panel)] p-3 ring-1 ring-[var(--line)]">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                          Previous repairs
                        </p>
                        {match.repairs.length === 0 ? (
                          <p className="mt-2 text-sm text-[var(--muted)]">No prior repairs</p>
                        ) : (
                          <ul className="asa-scroll mt-2 max-h-36 space-y-2 overflow-y-auto text-sm">
                            {match.repairs.slice(0, 5).map((r) => (
                              <li key={r.id} className="border-b border-[var(--line)] pb-2 last:border-0 last:pb-0">
                                <span className="font-medium">{r.service_type}</span>
                                <span className="block text-xs text-[var(--muted)]">
                                  ${Number(r.cost).toFixed(0)}
                                  {r.created_at
                                    ? ` · ${new Date(r.created_at).toLocaleDateString()}`
                                    : ""}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                      <div className="rounded-xl bg-[var(--accent-soft)]/50 p-3 ring-1 ring-[var(--accent)]/20">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--accent)]">
                          AI recommendation
                        </p>
                        <ul className="mt-2 space-y-2 text-sm text-[var(--muted)]">
                          {recommendations.map((tip) => (
                            <li key={tip} className="flex gap-2">
                              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--accent)]" />
                              <span>{tip}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  ) : null}
                </section>
              )}

              <section className="space-y-3">
                <SectionHeader
                  title="Service"
                  titleClassName="text-[var(--accent)]"
                  description="Choose from your Service Catalog. Tap a service to add or remove it."
                  compact
                />
                {services.length === 0 ? (
                  <p className="rounded-xl border border-[var(--line)] bg-[var(--background)]/60 px-3.5 py-3 text-sm text-[var(--muted)]">
                    No active services yet.{" "}
                    <Link
                      href="/dashboard/settings?tab=shop"
                      className="font-semibold text-[var(--accent)] hover:underline"
                    >
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
                          className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                            selected
                              ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)] shadow-[0_8px_20px_-14px_rgba(240,90,36,0.9)]"
                              : "border-[var(--line)] bg-white text-[var(--muted)] hover:border-[var(--accent)] hover:text-[var(--foreground)]"
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
                        className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-glow)]"
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
                          className="shrink-0 rounded-full border border-[var(--line)] px-3 text-sm text-[var(--muted)] transition hover:border-red-300 hover:text-red-700"
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
                  className="text-sm font-semibold text-[var(--accent)] hover:underline disabled:opacity-50"
                >
                  + Add another request
                </button>
              </section>
            </div>

            <div className="shrink-0 border-t border-[var(--line)] bg-[var(--panel)]/95 px-4 py-3 backdrop-blur-sm sm:px-5">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-xs text-[var(--muted)]">
                  {vinLooking
                    ? "Finishing vehicle lookup…"
                    : match?.customer
                      ? `Ready · ${match.customer.name}`
                      : "Ready to open a guest visit"}
                </p>
                <button
                  type="submit"
                  disabled={saving || vinLooking || services.length === 0}
                  className="btn-primary inline-flex min-w-[9.5rem] items-center justify-center gap-1.5 px-5 py-2.5 shadow-[0_14px_32px_-16px_rgba(240,90,36,0.85)] disabled:opacity-60"
                >
                  {!saving ? <IconPlay className="h-4 w-4" /> : null}
                  {saving ? "Starting…" : "Start Service"}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default function WalkInsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
          <div className="h-7 w-36 animate-pulse rounded-md bg-[var(--panel)]" />
          <div className="surface-panel h-11 animate-pulse" />
          <div className="surface-panel min-h-0 flex-1 animate-pulse" />
        </div>
      }
    >
      <WalkInsContent />
    </Suspense>
  );
}

function ModeChip({
  active,
  onClick,
  label,
  hint,
  icon,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  hint: string;
  icon: ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`min-w-0 flex-1 rounded-lg px-3 py-2 text-left transition ${
        active
          ? "bg-[var(--accent-soft)] shadow-[inset_0_0_0_1px_rgba(240,90,36,0.35)]"
          : "hover:bg-[var(--background)]"
      }`}
    >
      <span className="flex items-start gap-2.5">
        <span
          className={`mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md ${
            active
              ? "bg-[var(--panel)] text-[var(--accent)] ring-1 ring-[var(--accent)]/25"
              : "bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]"
          }`}
          aria-hidden
        >
          {icon}
        </span>
        <span className="min-w-0 flex-1">
          <span
            className={`block truncate text-sm font-semibold tracking-tight ${
              active ? "text-[var(--accent)]" : "text-[var(--foreground)]"
            }`}
          >
            {label}
          </span>
          <span className="mt-0.5 block truncate text-[11px] text-[var(--muted)]">{hint}</span>
        </span>
      </span>
    </button>
  );
}

function SectionHeader({
  eyebrow,
  title,
  titleClassName,
  description,
  compact,
}: {
  eyebrow?: string;
  title: string;
  titleClassName?: string;
  description: string;
  compact?: boolean;
}) {
  return (
    <div>
      {eyebrow ? <p className="section-label">{eyebrow}</p> : null}
      <h2
        className={`font-display font-semibold tracking-tight ${
          compact
            ? eyebrow
              ? "mt-1 text-base"
              : "text-base"
            : eyebrow
              ? "mt-1.5 text-lg"
              : "text-lg"
        }${titleClassName ? ` ${titleClassName}` : ""}`}
      >
        {title}
      </h2>
      <p className={`text-[var(--muted)] ${compact ? "mt-0.5 text-xs" : "mt-1 text-sm"}`}>
        {description}
      </p>
    </div>
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
      className={`rounded-xl border px-3.5 py-3 text-left transition ${
        active
          ? "border-[var(--accent)] bg-[var(--panel)] shadow-[0_12px_28px_-22px_rgba(240,90,36,0.85)] ring-1 ring-[var(--accent)]/25"
          : disabled
            ? "cursor-not-allowed border-[var(--line)] bg-[var(--background)]/40 opacity-55"
            : "border-[var(--line)] bg-[var(--panel)] hover:border-[var(--accent)]/50"
      }`}
    >
      <span className="flex items-center gap-2">
        <span
          className={`h-2 w-2 rounded-full ${
            active ? "bg-[var(--accent)]" : "bg-[var(--line)]"
          }`}
          aria-hidden
        />
        <span
          className={`text-sm font-semibold ${
            active ? "text-[var(--accent)]" : "text-[var(--foreground)]"
          }`}
        >
          {label}
        </span>
      </span>
      <span className="mt-1 block pl-4 text-xs text-[var(--muted)]">{description}</span>
    </button>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "converted"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : status === "open"
        ? "bg-[var(--accent-soft)] text-[var(--accent)] ring-[var(--accent)]/25"
        : "bg-[var(--background)] text-[var(--muted)] ring-[var(--line)]";
  return (
    <span
      className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ring-1 ${tone}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function visitInitials(complaint: string, linked: boolean): string {
  const first = complaint
    .split("\n")
    .map((s) => s.trim())
    .find(Boolean);
  if (first) {
    const parts = first.split(/\s+/).filter(Boolean);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  }
  return linked ? "C" : "?";
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
      <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
        {label}
      </span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none transition focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-glow)]"
      />
    </label>
  );
}

function IconScanVin({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <path
        d="M4 7V5a1 1 0 0 1 1-1h2M20 7V5a1 1 0 0 0-1-1h-2M4 17v2a1 1 0 0 0 1 1h2M20 17v2a1 1 0 0 1-1 1h-2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M8 12h1.5M11 12h2M14.5 12H16"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconNoVin({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <rect
        x="3.5"
        y="7.5"
        width="17"
        height="9"
        rx="2"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M7 12h3.5M13.5 12H17"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconQueue({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden className={className}>
      <path
        d="M5 7h14M5 12h10M5 17h7"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconPlay({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M7 4.5v15l13-7.5L7 4.5z" />
    </svg>
  );
}
