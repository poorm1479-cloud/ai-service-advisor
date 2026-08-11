"use client";

import dynamic from "next/dynamic";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/lib/auth";
import {
  createImportJob,
  DuplicateCandidate,
  getImportJob,
  ImportJob,
  ImportSourceInfo,
  inferFileImportSource,
  listImportJobs,
  listImportSources,
  resolveDuplicates,
  runImportJob,
  setManualSections,
  uploadImportFile,
} from "@/lib/imports";
import { getCustomerDetail } from "@/lib/crm";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { vinAssist } from "@/lib/walkin";

const VinInput = dynamic(
  () => import("@/components/VinInput").then((m) => ({ default: m.VinInput })),
  {
    ssr: false,
    loading: () => (
      <div className="h-10 animate-pulse rounded-md border border-[var(--line)] bg-[var(--background)]/60" />
    ),
  },
);

type WizardStep = "source" | "configure" | "progress" | "duplicates" | "report";
type DisplayStep = "Upload" | "Review" | "Import" | "Complete";

const DISPLAY_STEPS: DisplayStep[] = ["Upload", "Review", "Import", "Complete"];

const FILE_SOURCES = new Set(["csv", "excel"]);

const MERGE_ACTIONS = [
  { value: "merge", label: "Merge both" },
  { value: "keep_existing", label: "Keep existing only" },
  { value: "keep_incoming", label: "Use imported record" },
  { value: "skip", label: "Skip this import" },
];

const ENTITY_LABELS: Record<string, string> = {
  customer: "Customer",
  vehicle: "Vehicle",
  repair_history: "Repair history",
  invoice: "Invoice",
  estimate: "Estimate",
  appointment: "Appointment",
};

const MATCH_LABELS: Record<string, string> = {
  phone: "same phone number",
  email: "same email",
  name: "similar name",
  vin: "same VIN",
  license_plate: "same license plate",
  composite: "matching details",
};

const FIELD_LABELS: Record<string, string> = {
  name: "Name",
  phone: "Phone",
  email: "Email",
  address: "Address",
  external_id: "External ID",
  vin: "VIN",
  year: "Year",
  make: "Make",
  model: "Model",
  mileage: "Mileage",
  license_plate: "License plate",
};

const CUSTOMER_FIELD_ORDER = ["name", "phone", "email", "address", "external_id"];
const VEHICLE_FIELD_ORDER = [
  "year",
  "make",
  "model",
  "vin",
  "license_plate",
  "mileage",
  "external_id",
];

function displayStepFor(step: WizardStep): DisplayStep {
  if (step === "source") return "Upload";
  if (step === "configure") return "Review";
  if (step === "progress" || step === "duplicates") return "Import";
  return "Complete";
}

/** Map job API status → wizard step (terminal success/failure → Complete/report). */
function wizardStepForJob(job: ImportJob): WizardStep {
  const status = (job.status || "").toLowerCase();
  if (status === "awaiting_resolution") return "duplicates";
  // Successful or finished imports (incl. manual Save) open the Complete report view.
  if (
    status === "completed" ||
    status === "failed" ||
    status === "cancelled" ||
    job.report != null ||
    job.completed_at != null
  ) {
    return "report";
  }
  return "progress";
}

function jobStatusLabel(status: string): string {
  const s = (status || "").toLowerCase();
  if (s === "completed") return "Complete";
  if (s === "awaiting_resolution") return "Needs resolution";
  if (s === "failed") return "Failed";
  if (s === "cancelled") return "Cancelled";
  if (!s) return "—";
  return s.replace(/_/g, " ");
}

function entityImported(job: ImportJob, kind: string): number {
  return job.report?.entity_counts?.[kind]?.imported ?? job.batch_counts?.[kind] ?? 0;
}

function duplicatesResolved(job: ImportJob): number {
  if (job.report) return job.report.duplicates_resolved;
  return job.duplicates.filter((d) => d.resolved).length;
}

function formatJobCreated(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function jobCountsSummary(job: ImportJob): string {
  const customers = entityImported(job, "customer");
  const vehicles = entityImported(job, "vehicle");
  const repairs = entityImported(job, "repair_history");
  const duplicates = duplicatesResolved(job);
  return `${customers} cust · ${vehicles} veh · ${repairs} repair · ${duplicates} dup`;
}

type ManualCustomerForm = {
  name: string;
  phone: string;
  email: string;
};

type ManualVehicleForm = {
  year: string;
  make: string;
  model: string;
  mileage: string;
  vin: string;
};

const EMPTY_CUSTOMER: ManualCustomerForm = { name: "", phone: "", email: "" };
const EMPTY_VEHICLE: ManualVehicleForm = {
  year: "",
  make: "",
  model: "",
  mileage: "",
  vin: "",
};

/** Build the existing manual-import JSON sections from form fields. */
function buildManualSections(
  customer: ManualCustomerForm,
  vehicle: ManualVehicleForm,
): Record<string, Record<string, unknown>[]> {
  const sections: Record<string, Record<string, unknown>[]> = {};

  const name = customer.name.trim();
  const phone = customer.phone.trim();
  const email = customer.email.trim();
  if (name || phone || email) {
    if (!name) throw new Error("Customer name is required");
    if (!phone) throw new Error("Customer phone is required");
    const row: Record<string, unknown> = { name, phone };
    if (email) row.email = email;
    sections.customers = [row];
  }

  const year = vehicle.year.trim();
  const make = vehicle.make.trim();
  const model = vehicle.model.trim();
  const mileage = vehicle.mileage.trim();
  const vin = vehicle.vin.replace(/[\s-]/g, "").toUpperCase();
  if (year || make || model || mileage || vin) {
    if (!year) throw new Error("Vehicle year is required");
    if (!make) throw new Error("Vehicle make is required");
    if (!model) throw new Error("Vehicle model is required");
    if (!mileage) throw new Error("Vehicle mileage is required");
    const yearNum = Number(year);
    const mileageNum = Number(mileage);
    if (!Number.isFinite(yearNum)) throw new Error("Vehicle year must be a number");
    if (!Number.isFinite(mileageNum)) throw new Error("Vehicle mileage must be a number");
    const row: Record<string, unknown> = {
      year: yearNum,
      make,
      model,
      mileage: mileageNum,
    };
    if (vin) row.vin = vin;
    sections.vehicles = [row];
  }

  if (!sections.customers && !sections.vehicles) {
    throw new Error("Enter a customer and/or vehicle to import");
  }

  return sections;
}

function ManualField({
  label,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        {label}
      </span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-[var(--line)] bg-[var(--background)]/40 px-3 py-2 text-sm"
      />
    </label>
  );
}

function StatusBadge({ status }: { status: string }) {
  const s = (status || "").toLowerCase();
  const tone =
    s === "completed"
      ? "bg-emerald-50 text-emerald-800 ring-emerald-200/80"
      : s === "failed" || s === "cancelled"
        ? "bg-red-50 text-red-700 ring-red-200/80"
        : s === "awaiting_resolution"
          ? "bg-amber-50 text-amber-800 ring-amber-200/80"
          : "bg-[var(--accent-soft)] text-[var(--accent)] ring-[var(--accent)]/20";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize ring-1 ring-inset ${tone}`}
    >
      {jobStatusLabel(status)}
    </span>
  );
}

function StepRail({ active }: { active: DisplayStep }) {
  const activeIdx = DISPLAY_STEPS.indexOf(active);
  return (
    <ol className="surface-panel flex shrink-0 items-center gap-1 overflow-x-auto p-2 sm:gap-0 sm:p-1.5">
      {DISPLAY_STEPS.map((label, idx) => {
        const done = idx < activeIdx;
        const current = idx === activeIdx;
        return (
          <li key={label} className="flex min-w-0 flex-1 items-center">
            <div
              className={`flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 transition-colors ${
                current ? "bg-[var(--accent-soft)]" : done ? "bg-transparent" : ""
              }`}
            >
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold tabular-nums ${
                  current
                    ? "bg-[var(--accent)] text-white shadow-[0_8px_20px_-10px_rgba(240,90,36,0.9)]"
                    : done
                      ? "bg-[var(--ink)] text-white"
                      : "bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]"
                }`}
              >
                {done ? (
                  <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
                    <path
                      fill="currentColor"
                      d="M6.5 11.2 3.3 8l1.1-1.1 2.1 2.1 4.6-4.6L12.2 5.5 6.5 11.2z"
                    />
                  </svg>
                ) : (
                  idx + 1
                )}
              </span>
              <span
                className={`truncate text-[11px] font-semibold uppercase tracking-[0.14em] ${
                  current ? "text-[var(--accent)]" : done ? "text-[var(--foreground)]" : "text-[var(--muted)]"
                }`}
              >
                {label}
              </span>
            </div>
            {idx < DISPLAY_STEPS.length - 1 && (
              <span
                className={`mx-0.5 hidden h-px w-4 shrink-0 sm:block sm:w-6 ${
                  done ? "bg-[var(--ink)]/40" : "bg-[var(--line)]"
                }`}
                aria-hidden
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

function SourceOptionCard({
  title,
  description,
  selected,
  onClick,
  icon,
}: {
  title: string;
  description: string;
  selected?: boolean;
  onClick: () => void;
  icon: "file" | "manual";
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative overflow-hidden rounded-2xl border bg-[var(--panel)] p-5 text-left shadow-[var(--shadow-soft)] transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--accent)] ${
        selected ? "border-[var(--accent)] ring-2 ring-[var(--accent)]/15" : "border-[var(--line)]"
      }`}
    >
      <div
        className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-[radial-gradient(circle,rgba(240,90,36,0.14),transparent_68%)] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        aria-hidden
      />
      <div className="relative flex items-start gap-4">
        <span
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
            selected
              ? "bg-[var(--accent)] text-white"
              : "bg-[var(--background)] text-[var(--foreground)] ring-1 ring-[var(--line)] group-hover:bg-[var(--accent-soft)] group-hover:text-[var(--accent)]"
          }`}
        >
          {icon === "file" ? (
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M8 4h6l4 4v12H8V4z" />
              <path d="M14 4v4h4" />
              <path d="M10 13h6M10 17h4" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M5 19h14" />
              <path d="M7 15.5 16.5 6a1.8 1.8 0 0 1 2.5 2.5L9.5 18l-4 1 1.5-3.5z" />
            </svg>
          )}
        </span>
        <div className="min-w-0">
          <p className="font-display text-base font-semibold tracking-tight">{title}</p>
          <p className="mt-1 text-sm leading-relaxed text-[var(--muted)]">{description}</p>
        </div>
      </div>
    </button>
  );
}

function IconCancel({ className = "h-4 w-4" }: { className?: string }) {
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
      <circle cx="12" cy="12" r="9" />
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </svg>
  );
}

function IconApply({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

function IconContinue({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

function IconSave({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" />
      <path d="M17 21v-8H7v8" />
      <path d="M7 3v5h8" />
    </svg>
  );
}

function IconImportPlus({ className = "h-5 w-5" }: { className?: string }) {
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
      {/* Document left, + on the right — extra gap vs IconUserPlus */}
      <path d="M7.5 3H4A2 2 0 0 0 2 5v14a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2V9L9.5 3H7.5z" />
      <path d="M9.5 3v5h4" />
      <path d="M5 13h5.5M5 16.5h3.5" />
      <path d="M20 8v6M17 11h6" />
    </svg>
  );
}

function IconCsv({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
      <path d="M14 3v5h5" />
      <path d="M8 13h8" />
      <path d="M8 17h5" />
    </svg>
  );
}

function IconExcel({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
      <path d="M14 3v5h5" />
      <path d="m9.5 12.5 5 5" />
      <path d="m14.5 12.5-5 5" />
    </svg>
  );
}

function IconImport({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z" />
    </svg>
  );
}

function IconUpload({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M12 16V5" />
      <path d="m8 9 4-4 4 4" />
      <path d="M4 19h16" />
    </svg>
  );
}

function IconManual({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M5 19h14" />
      <path d="M7 15.5 16.5 6a1.8 1.8 0 0 1 2.5 2.5L9.5 18l-4 1 1.5-3.5z" />
    </svg>
  );
}

function IconHistory({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function JobSourceIcon({ source, className = "h-4 w-4" }: { source: string; className?: string }) {
  const s = (source || "").toLowerCase();
  if (s === "excel") return <IconExcel className={className} />;
  if (s === "csv") return <IconCsv className={className} />;
  if (s === "manual") return <IconManual className={className} />;
  return <IconUpload className={className} />;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ImportPage() {
  const { session, loading: authLoading } = useAuth();
  const [sources, setSources] = useState<ImportSourceInfo[]>([]);
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [step, setStep] = useState<WizardStep>("source");
  const [source, setSource] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [ocrText, setOcrText] = useState("");
  const [manualCustomer, setManualCustomer] = useState<ManualCustomerForm>(EMPTY_CUSTOMER);
  const [manualVehicle, setManualVehicle] = useState<ManualVehicleForm>(EMPTY_VEHICLE);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [primaryGroup, setPrimaryGroup] = useState<"file" | null>(null);
  const [vinStatus, setVinStatus] = useState<string | null>(null);
  const [vinLooking, setVinLooking] = useState(false);
  const [portalReady, setPortalReady] = useState(false);
  const [fileDragOver, setFileDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const vinAssistSeq = useRef(0);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  const selectedSource = useMemo(
    () => sources.find((s) => s.source === source) ?? null,
    [sources, source],
  );

  const fileSources = useMemo(
    () => sources.filter((s) => FILE_SOURCES.has(s.source)),
    [sources],
  );
  const manualSource = useMemo(
    () => sources.find((s) => s.source === "manual") ?? null,
    [sources],
  );

  const activeDisplayStep = displayStepFor(step);

  function clearManualForms() {
    vinAssistSeq.current += 1;
    setManualCustomer(EMPTY_CUSTOMER);
    setManualVehicle(EMPTY_VEHICLE);
    setVinStatus(null);
    setVinLooking(false);
  }

  const refreshJobs = useCallback(async () => {
    setJobs(await listImportJobs());
  }, []);

  /** VIN scan/type → auto-fill year/make/model (and CRM customer when known). */
  useEffect(() => {
    if (source !== "manual" || step !== "configure") return;

    const cleaned = manualVehicle.vin.replace(/[\s-]/g, "").toUpperCase();
    if (cleaned.length !== 17) {
      setVinStatus(null);
      setVinLooking(false);
      return;
    }

    const seq = ++vinAssistSeq.current;
    const timer = window.setTimeout(() => {
      void (async () => {
        setVinLooking(true);
        try {
          const assist = await vinAssist(cleaned);
          if (seq !== vinAssistSeq.current) return;

          if (assist.existing) {
            const v = assist.existing;
            setManualVehicle((prev) => ({
              ...prev,
              vin: v.vin,
              year: String(v.year),
              make: v.make,
              model: v.model,
              mileage: prev.mileage.trim() ? prev.mileage : String(v.mileage),
            }));
            if (v.customer_id) {
              try {
                const detail = await getCustomerDetail(v.customer_id);
                if (seq !== vinAssistSeq.current) return;
                const c = detail.customer;
                setManualCustomer((prev) => ({
                  name: prev.name.trim() ? prev.name : c.name,
                  phone: prev.phone.trim() ? prev.phone : formatPhoneInput(c.phone ?? ""),
                  email: prev.email.trim() ? prev.email : (c.email ?? ""),
                }));
              } catch {
                // Customer hydrate is best-effort
              }
            }
          } else if (assist.decoded) {
            const d = assist.decoded;
            setManualVehicle((prev) => ({
              ...prev,
              vin: d.vin,
              year: String(d.year),
              make: d.make,
              model: d.model,
            }));
          }
          setVinStatus(assist.message);
        } catch (err) {
          if (seq !== vinAssistSeq.current) return;
          setVinStatus(err instanceof Error ? err.message : "VIN lookup failed");
        } finally {
          if (seq === vinAssistSeq.current) setVinLooking(false);
        }
      })();
    }, 350);

    return () => window.clearTimeout(timer);
  }, [manualVehicle.vin, source, step]);

  useEffect(() => {
    if (authLoading || !session || session.role !== "owner") return;
    void (async () => {
      try {
        setSources(await listImportSources());
        await refreshJobs();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load import sources");
      }
    })();
  }, [authLoading, session, refreshJobs]);

  useEffect(() => {
    if (!job || step !== "progress") return;
    if (["completed", "failed", "awaiting_resolution"].includes(job.status)) return;
    const t = setInterval(() => {
      void (async () => {
        try {
          const next = await getImportJob(job.id);
          setJob(next);
          if (next.status === "awaiting_resolution") {
            setResolutions(
              Object.fromEntries(
                next.duplicates
                  .filter((d) => !d.resolved)
                  .map((d) => [d.id, d.suggested_action]),
              ),
            );
            setStep("duplicates");
          } else if (next.status === "completed" || next.status === "failed") {
            setStep("report");
            await refreshJobs();
          }
        } catch {
          /* ignore poll errors */
        }
      })();
    }, 1200);
    return () => clearInterval(t);
  }, [job, step, refreshJobs]);

  function selectSource(next: string) {
    setSource(next);
    setPrimaryGroup(null);
    setStep("configure");
  }

  function formatManualSaveResult(ran: ImportJob): string {
    const customers = entityImported(ran, "customer");
    const vehicles = entityImported(ran, "vehicle");
    const parts: string[] = [];
    if (customers > 0) parts.push(`${customers} customer${customers === 1 ? "" : "s"}`);
    if (vehicles > 0) parts.push(`${vehicles} vehicle${vehicles === 1 ? "" : "s"}`);
    if (parts.length === 0) {
      return ran.status === "failed"
        ? ran.error || "Save failed"
        : "Saved — no new records imported";
    }
    return `Saved ${parts.join(" and ")}`;
  }

  /** Manual Entry: save, show result, clear form, stay ready for next entry. */
  async function saveManualEntry() {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const sections = buildManualSections(manualCustomer, manualVehicle);
      let created = await createImportJob({ source: "manual", options: {}, credentials: {} });
      setJob(created);
      created = await setManualSections(created.id, sections);
      setJob(created);

      const ran = await runImportJob(created.id, false);
      setJob(ran);
      await refreshJobs();

      if (ran.status === "awaiting_resolution") {
        setResolutions(
          Object.fromEntries(
            ran.duplicates.filter((d) => !d.resolved).map((d) => [d.id, d.suggested_action]),
          ),
        );
        clearManualForms();
        setStep("duplicates");
        return;
      }

      if (ran.status === "failed") {
        setError(formatManualSaveResult(ran));
        return;
      }

      setSuccess(formatManualSaveResult(ran));
      clearManualForms();
      setStep("configure");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
      setStep("configure");
    } finally {
      setBusy(false);
    }
  }

  async function runImportPipeline() {
    if (!source) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      let activeSource = source;
      // Spreadsheet uploads: selected CSV/Excel connector must match the file type.
      if (FILE_SOURCES.has(source) || primaryGroup === "file") {
        if (!file) throw new Error("Upload a CSV or Excel file to continue");
        const inferred = inferFileImportSource(file.name);
        if (!inferred) {
          throw new Error("Unsupported file type. Use .csv or .xlsx");
        }
        if (FILE_SOURCES.has(source) && inferred !== source) {
          throw new Error(
            source === "excel"
              ? "Upload an Excel file (.xlsx) for this import"
              : "Upload a CSV file for this import",
          );
        }
        activeSource = inferred;
        setSource(inferred);
      }

      const activeMeta = sources.find((s) => s.source === activeSource) ?? selectedSource;
      const options: Record<string, unknown> = {};
      if (activeSource === "ocr" && ocrText) options.ocr_text = ocrText;

      // Show progress pane immediately (avoids stuck "Starting…" on the review form).
      setStep("progress");

      let created = await createImportJob({ source: activeSource, options, credentials: {} });
      setJob(created);

      if (activeMeta?.requires_upload || FILE_SOURCES.has(activeSource)) {
        if (file) {
          created = await uploadImportFile(created.id, file, ocrText || undefined);
          setJob(created);
        } else if (activeSource === "ocr" && ocrText) {
          // ocr_text already in job options from create
        } else if (activeSource !== "ocr") {
          throw new Error("Upload a file to continue");
        } else {
          throw new Error("Provide OCR text or upload a text dump");
        }
      }

      setStep("progress");
      const ran = await runImportJob(created.id, false);
      setJob(ran);
      if (ran.status === "awaiting_resolution") {
        setResolutions(
          Object.fromEntries(
            ran.duplicates.filter((d) => !d.resolved).map((d) => [d.id, d.suggested_action]),
          ),
        );
        setStep("duplicates");
      } else if (ran.status === "completed" || ran.status === "failed") {
        setStep("report");
        await refreshJobs();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
      setStep("configure");
    } finally {
      setBusy(false);
    }
  }

  async function startImport(e: FormEvent) {
    e.preventDefault();
    if (!source) return;

    if (source === "manual") {
      await saveManualEntry();
      return;
    }

    await runImportPipeline();
  }

  async function submitResolutions() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const payload = Object.entries(resolutions).map(([duplicate_id, action]) => ({
        duplicate_id,
        action,
      }));
      const next = await resolveDuplicates(job.id, payload, true);
      setJob(next);
      await refreshJobs();
      // Manual Entry: return to empty form after resolving so more records can be added.
      if (next.source === "manual") {
        setSuccess(formatManualSaveResult(next));
        clearManualForms();
        setStep("configure");
        setSource("manual");
      } else {
        setStep("report");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve duplicates");
    } finally {
      setBusy(false);
    }
  }

  function clearSelectedFile() {
    setFile(null);
    setFileDragOver(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function applySpreadsheetFile(next: File) {
    const inferred = inferFileImportSource(next.name);
    if (!inferred) {
      setError("Unsupported file type. Use .csv or .xlsx");
      clearSelectedFile();
      return;
    }
    if (FILE_SOURCES.has(source) && inferred !== source) {
      setError(
        source === "excel"
          ? "This step expects an Excel file (.xlsx). Choose CSV for .csv uploads."
          : "This step expects a CSV file. Choose Excel for .xlsx uploads.",
      );
      clearSelectedFile();
      return;
    }
    setError(null);
    setFile(next);
  }

  function resetWizard() {
    setStep("source");
    setSource("");
    clearSelectedFile();
    setJob(null);
    setError(null);
    setSuccess(null);
    clearManualForms();
    setPrimaryGroup(null);
  }

  /** Open a past job from Recent jobs (manual success → Complete report). */
  async function openRecentJob(j: ImportJob) {
    setError(null);
    setSuccess(null);
    setPrimaryGroup(null);
    setSource(j.source);
    try {
      const full = await getImportJob(j.id);
      setJob(full);
      const next = wizardStepForJob(full);
      if (next === "duplicates") {
        setResolutions(
          Object.fromEntries(
            full.duplicates
              .filter((d) => !d.resolved)
              .map((d) => [d.id, d.suggested_action]),
          ),
        );
      }
      setStep(next);
    } catch {
      setJob(j);
      setStep(wizardStepForJob(j));
    }
  }

  if (!authLoading && session && session.role !== "owner") {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col gap-5 overflow-hidden">
        <div className="flex items-center gap-2">
          <IconImport className="h-5 w-5 shrink-0 text-[var(--muted)]" />
          <h1 className="page-title">Import</h1>
        </div>
        <p className="surface-panel max-w-lg border-amber-200/80 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Only shop owners can import data.
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-5 overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div className="hero-motion min-w-0">
          <div className="flex items-center gap-2">
            <IconImport className="h-5 w-5 shrink-0 text-[var(--muted)]" />
            <h1 className="page-title">Import</h1>
          </div>
          <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-[var(--muted)]">
            Bring in shop history so AI can advise with real customer and vehicle context.
          </p>
        </div>
        {step !== "source" && (
          <button
            type="button"
            onClick={resetWizard}
            aria-label="New import"
            className="btn-primary inline-flex h-10 w-10 items-center justify-center p-0 shadow-[0_14px_32px_-16px_rgba(240,90,36,0.85)]"
          >
            <IconImportPlus className="h-5 w-5" />
          </button>
        )}
      </div>

      <div className="hero-motion-delay shrink-0">
        <StepRail active={activeDisplayStep} />
      </div>

      {error && (
        <p className="shrink-0 rounded-xl border border-red-200/80 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {success && (
        <p className="shrink-0 rounded-xl border border-emerald-200/80 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {success}
        </p>
      )}

      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-6 overflow-hidden pb-2">
      {step === "source" && (
        <section className="hero-motion-late shrink-0 space-y-5">
          <aside className="relative overflow-hidden rounded-2xl border border-[var(--accent)]/20 bg-[linear-gradient(145deg,#fff8f3_0%,#ffefe6_45%,#ffe6d8_100%)] px-5 py-5 shadow-[var(--shadow-soft)] sm:px-6">
            <div
              className="pointer-events-none absolute -right-10 -top-16 h-44 w-44 rounded-full bg-[radial-gradient(circle,rgba(240,90,36,0.14),transparent_70%)]"
              aria-hidden
            />
            <div
              className="pointer-events-none absolute -bottom-12 -left-8 h-36 w-36 rounded-full bg-[radial-gradient(circle,rgba(255,133,65,0.1),transparent_68%)]"
              aria-hidden
            />
            <div className="relative">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--accent-hover)]">
                AI Import Assistant
              </p>
              <h2 className="font-display mt-2 text-xl font-semibold tracking-tight text-[var(--ink)] sm:text-2xl">
                History becomes context
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-[var(--ink)]/60">
                While importing, AI detects customers, matches vehicles, builds repair history, and creates lasting memory for better advice.
              </p>
              <ul className="mt-4 flex flex-wrap gap-2">
                {["Detect customers", "Match vehicles", "Build history", "Create memory"].map(
                  (item) => (
                    <li
                      key={item}
                      className="rounded-full border border-[var(--accent)]/25 bg-white/65 px-3 py-1 text-[11px] font-medium tracking-wide text-[var(--accent-hover)] shadow-[0_1px_0_rgba(255,255,255,0.7)]"
                    >
                      {item}
                    </li>
                  ),
                )}
              </ul>
            </div>
          </aside>

          <div className="grid gap-3 sm:grid-cols-2">
            <SourceOptionCard
              title="CSV / Excel"
              description="Upload spreadsheet exports from your shop system"
              selected={primaryGroup === "file"}
              icon="file"
              onClick={() => {
                setPrimaryGroup("file");
                setSource(fileSources[0]?.source ?? "csv");
              }}
            />

            {manualSource && (
              <SourceOptionCard
                title="Manual Entry"
                description="Enter a customer and vehicle with guided forms"
                icon="manual"
                onClick={() => {
                  setSuccess(null);
                  setError(null);
                  selectSource("manual");
                }}
              />
            )}
          </div>
        </section>
      )}

      {/* Portaled overlays escape overflow-hidden shells so dim covers header + page chrome */}
      {portalReady &&
        primaryGroup === "file" &&
        step === "source" &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
            role="dialog"
            aria-modal="true"
            aria-labelledby="file-import-dialog-title"
            onClick={() => {
              setPrimaryGroup(null);
              setSource("");
              clearSelectedFile();
            }}
          >
            <div
              className="flex w-full max-w-[24rem] flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-4 pb-3.5 pt-4">
                <div
                  className="pointer-events-none absolute right-0 top-0 h-32 w-32 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                  aria-hidden="true"
                />
                <div className="relative">
                  <p
                    id="file-import-dialog-title"
                    className="text-base font-semibold tracking-tight text-[var(--ink)]"
                  >
                    Select file type
                  </p>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    Choose CSV or Excel, then continue to upload.
                  </p>
                </div>
              </div>
              <div className="space-y-3.5 px-4 py-4">
                <div className="grid grid-cols-2 gap-2">
                  {fileSources.map((s) => {
                    const selected = source === s.source;
                    const FileIcon = s.source === "excel" ? IconExcel : IconCsv;
                    return (
                      <button
                        key={s.source}
                        type="button"
                        onClick={() => {
                          if (source !== s.source) clearSelectedFile();
                          setSource(s.source);
                        }}
                        className={`flex flex-col items-center gap-1.5 rounded-lg border px-2.5 py-3.5 text-sm font-medium transition-colors ${
                          selected
                            ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                            : "border-[var(--line)] hover:border-[var(--accent)]/50"
                        }`}
                      >
                        <span
                          className={`inline-flex h-9 w-9 items-center justify-center rounded-lg ${
                            selected
                              ? "bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]"
                              : "bg-[var(--background)] text-[var(--foreground)] ring-1 ring-[var(--line)]"
                          }`}
                        >
                          <FileIcon className="h-4 w-4" />
                        </span>
                        {s.label}
                      </button>
                    );
                  })}
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPrimaryGroup(null);
                      setSource("");
                      clearSelectedFile();
                    }}
                    className="btn-ghost inline-flex items-center justify-center gap-1.5 px-3.5 py-1.5 text-sm"
                  >
                    <IconCancel />
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={!source || !FILE_SOURCES.has(source)}
                    onClick={() => setStep("configure")}
                    className="btn-primary inline-flex items-center justify-center gap-1.5 px-3.5 py-1.5 text-sm disabled:opacity-60"
                  >
                    Continue
                    <IconContinue />
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {portalReady &&
        step === "configure" &&
        selectedSource &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
            role="dialog"
            aria-modal="true"
            aria-labelledby="import-review-dialog-title"
            onClick={() => {
              setStep("source");
              setPrimaryGroup(null);
              setFileDragOver(false);
            }}
          >
            <form
              onSubmit={startImport}
              onClick={(e) => e.stopPropagation()}
              className={`asa-scroll flex w-full flex-col overflow-hidden overscroll-contain border border-[var(--line)] bg-[var(--panel)] shadow-[0_28px_80px_-20px_rgba(15,23,42,0.55)] ${
                FILE_SOURCES.has(source)
                  ? "max-w-[24rem] rounded-xl"
                  : source === "manual"
                    ? "max-h-[min(88vh,36rem)] max-w-md rounded-xl"
                    : "max-h-[min(92vh,44rem)] max-w-2xl rounded-2xl"
              }`}
            >
              <div
                className={`relative shrink-0 border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white ${
                  FILE_SOURCES.has(source) || source === "manual"
                    ? "px-4 py-3.5"
                    : "px-5 py-6 sm:px-6"
                }`}
              >
                <div
                  className={`pointer-events-none absolute rounded-full bg-[var(--accent-glow)] blur-2xl ${
                    FILE_SOURCES.has(source) || source === "manual"
                      ? "-right-4 -top-8 h-32 w-32"
                      : "-right-6 -top-10 h-40 w-40"
                  }`}
                  aria-hidden="true"
                />
                <div
                  className={`relative flex ${
                    FILE_SOURCES.has(source) || source === "manual"
                      ? "items-center gap-3"
                      : "items-start gap-3.5"
                  }`}
                >
                  {FILE_SOURCES.has(source) ? (
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)] text-white shadow-[0_8px_20px_-8px_rgba(240,90,36,0.85)]">
                      {source === "excel" ? <IconExcel className="h-4 w-4" /> : <IconCsv className="h-4 w-4" />}
                    </span>
                  ) : null}
                  <div className="min-w-0 flex items-center">
                    {source === "manual" ? (
                      <div>
                        <h2
                          id="import-review-dialog-title"
                          className="font-display text-base font-semibold tracking-tight text-[var(--ink)]"
                        >
                          Manual Entry
                        </h2>
                        <p className="mt-0.5 text-xs leading-relaxed text-[var(--muted)]">
                          Enter a customer and/or vehicle, then save.
                        </p>
                      </div>
                    ) : (
                      <h2
                        id="import-review-dialog-title"
                        className={`font-display font-semibold leading-none tracking-tight text-[var(--ink)] ${
                          FILE_SOURCES.has(source) ? "text-base" : "text-xl"
                        }`}
                      >
                        {FILE_SOURCES.has(source) ? "Review" : selectedSource.label}
                      </h2>
                    )}
                  </div>
                </div>
              </div>

              <div
                className={
                  FILE_SOURCES.has(source)
                    ? "px-4 py-4"
                    : source === "manual"
                      ? "asa-scroll min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3.5"
                      : "asa-scroll min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-6"
                }
              >
                {selectedSource.requires_upload && FILE_SOURCES.has(source) && (
                  <div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept={
                        source === "excel"
                          ? ".xlsx,.xlsm,.xltx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                          : ".csv,.tsv,.txt,text/csv,text/tab-separated-values"
                      }
                      className="sr-only"
                      onChange={(e) => {
                        const next = e.target.files?.[0] ?? null;
                        if (!next) {
                          clearSelectedFile();
                          return;
                        }
                        applySpreadsheetFile(next);
                      }}
                    />
                    {!file ? (
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        onDragEnter={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setFileDragOver(true);
                        }}
                        onDragOver={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setFileDragOver(true);
                        }}
                        onDragLeave={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setFileDragOver(false);
                        }}
                        onDrop={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setFileDragOver(false);
                          const next = e.dataTransfer.files?.[0] ?? null;
                          if (!next) return;
                          applySpreadsheetFile(next);
                        }}
                        className={`group relative flex w-full flex-col items-center justify-center rounded-xl border border-dashed px-4 py-6 text-center transition-colors ${
                          fileDragOver
                            ? "border-[var(--accent)] bg-[var(--accent-soft)]"
                            : "border-[var(--line)] bg-[var(--background)]/45 hover:border-[var(--accent)]/55 hover:bg-[var(--accent-soft)]/40"
                        }`}
                      >
                        <div
                          className="pointer-events-none absolute inset-x-0 top-0 h-16 rounded-t-xl bg-[radial-gradient(circle_at_50%_0%,var(--accent-glow),transparent_70%)] opacity-50"
                          aria-hidden
                        />
                        <span
                          className={`relative inline-flex h-10 w-10 items-center justify-center rounded-lg transition-colors ${
                            fileDragOver
                              ? "bg-[var(--accent)] text-white shadow-lg shadow-[var(--accent-glow)]"
                              : "bg-white text-[var(--accent)] ring-1 ring-[var(--line)] group-hover:bg-[var(--accent)] group-hover:text-white group-hover:shadow-md group-hover:shadow-[var(--accent-glow)] group-hover:ring-0"
                          }`}
                        >
                          <IconUpload className="h-4 w-4" />
                        </span>
                        <p className="relative mt-2.5 font-display text-sm font-semibold tracking-tight text-[var(--ink)]">
                          {fileDragOver
                            ? "Drop to upload"
                            : source === "excel"
                              ? "Import the Excel file"
                              : "Import the CSV file"}
                        </p>
                      </button>
                    ) : (
                      <div className="relative overflow-hidden rounded-xl border border-[var(--line)] bg-[linear-gradient(135deg,#111_0%,#1c1c1c_55%,#2a1810_100%)] px-4 py-4 text-white shadow-[var(--shadow-soft)]">
                        <div
                          className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-[radial-gradient(circle,rgba(240,90,36,0.4),transparent_70%)]"
                          aria-hidden
                        />
                        <div className="relative flex items-center gap-3">
                          <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/15">
                            {source === "excel" ? (
                              <IconExcel className="h-4 w-4 text-[var(--rail-active-fg)]" />
                            ) : (
                              <IconCsv className="h-4 w-4 text-[var(--rail-active-fg)]" />
                            )}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-display text-sm font-semibold tracking-tight">
                              {file.name}
                            </p>
                            <p className="mt-1 text-xs leading-none text-white/55">
                              {formatFileSize(file.size)} · {source.toUpperCase()} connector
                            </p>
                          </div>
                          <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-400/20 text-emerald-300 ring-1 ring-emerald-400/30">
                            <svg viewBox="0 0 16 16" className="h-3 w-3" aria-hidden>
                              <path
                                fill="currentColor"
                                d="M6.5 11.2 3.3 8l1.1-1.1 2.1 2.1 4.6-4.6L12.2 5.5 6.5 11.2z"
                              />
                            </svg>
                          </span>
                        </div>
                        <div className="relative mt-3 flex flex-wrap gap-1.5">
                          <button
                            type="button"
                            onClick={() => fileInputRef.current?.click()}
                            className="rounded-lg bg-white/10 px-2.5 py-1 text-xs font-semibold text-white ring-1 ring-white/15 transition-colors hover:bg-white/15"
                          >
                            Replace file
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              clearSelectedFile();
                            }}
                            className="rounded-lg px-2.5 py-1 text-xs font-semibold text-white/70 transition-colors hover:bg-white/10 hover:text-white"
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {selectedSource.requires_upload && !FILE_SOURCES.has(source) && (
                  <div className="space-y-3 rounded-xl border border-dashed border-[var(--line)] bg-[var(--background)]/50 p-4">
                    <input
                      type="file"
                      accept={
                        source === "pdf" ? ".pdf,application/pdf" : "*/*"
                      }
                      onChange={(e) => {
                        setFile(e.target.files?.[0] ?? null);
                      }}
                      className="block w-full text-sm file:mr-3 file:rounded-full file:border-0 file:bg-[var(--accent-soft)] file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-[var(--accent)]"
                    />
                    {(source === "ocr" || source === "pdf") && (
                      <textarea
                        className="min-h-28 w-full rounded-xl border border-[var(--line)] bg-transparent px-3.5 py-2.5 text-sm"
                        placeholder="OCR / document text (optional for PDF; required for OCR without file)"
                        value={ocrText}
                        onChange={(e) => setOcrText(e.target.value)}
                      />
                    )}
                  </div>
                )}

                {source === "manual" && (
                  <div className="space-y-3">
                    <div className="space-y-2.5 rounded-lg border border-[var(--line)] bg-[var(--background)]/35 p-3">
                      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                        Customer
                      </h3>
                      <div className="grid gap-2.5 sm:grid-cols-2">
                        <ManualField
                          label="Name"
                          value={manualCustomer.name}
                          onChange={(name) => setManualCustomer((c) => ({ ...c, name }))}
                          autoComplete="name"
                          placeholder="Sam Chen"
                        />
                        <ManualField
                          label="Phone"
                          value={manualCustomer.phone}
                          onChange={(phone) =>
                            setManualCustomer((c) => ({ ...c, phone: formatPhoneInput(phone) }))
                          }
                          type="tel"
                          autoComplete="tel"
                          placeholder={PHONE_PLACEHOLDER}
                        />
                        <div className="sm:col-span-2">
                          <ManualField
                            label="Email (optional)"
                            value={manualCustomer.email}
                            onChange={(email) => setManualCustomer((c) => ({ ...c, email }))}
                            type="email"
                            autoComplete="email"
                            placeholder="sam@example.com"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2.5 rounded-lg border border-[var(--line)] bg-[var(--background)]/35 p-3">
                      <h3 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                        Vehicle
                      </h3>
                      <p className="text-xs text-[var(--muted)]">
                        Scan or type a 17-character VIN to auto-fill year, make, and model.
                      </p>
                      <div className="grid gap-2.5 sm:grid-cols-2">
                        <div className="sm:col-span-2">
                          <VinInput
                            value={manualVehicle.vin}
                            onChange={(vin) => setManualVehicle((v) => ({ ...v, vin }))}
                            status={vinStatus}
                            looking={vinLooking}
                            required={false}
                          />
                        </div>
                        <ManualField
                          label="Year"
                          value={manualVehicle.year}
                          onChange={(year) => setManualVehicle((v) => ({ ...v, year }))}
                          type="number"
                          placeholder="2018"
                        />
                        <ManualField
                          label="Make"
                          value={manualVehicle.make}
                          onChange={(make) => setManualVehicle((v) => ({ ...v, make }))}
                          placeholder="Honda"
                        />
                        <ManualField
                          label="Model"
                          value={manualVehicle.model}
                          onChange={(model) => setManualVehicle((v) => ({ ...v, model }))}
                          placeholder="Accord"
                        />
                        <ManualField
                          label="Mileage"
                          value={manualVehicle.mileage}
                          onChange={(mileage) => setManualVehicle((v) => ({ ...v, mileage }))}
                          type="number"
                          placeholder="54000"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div
                className={`flex shrink-0 items-center gap-3 border-t border-[var(--line)] bg-[var(--background)]/35 ${
                  source === "manual" ? "justify-end" : "justify-between"
                } ${
                  FILE_SOURCES.has(source) || source === "manual"
                    ? "px-4 py-3.5"
                    : "px-5 py-4 sm:px-6"
                }`}
              >
                {source === "manual" ? (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setStep("source");
                        setPrimaryGroup(null);
                        setFileDragOver(false);
                      }}
                      className="btn-ghost inline-flex items-center justify-center gap-1.5 px-3.5 py-1.5 text-sm"
                    >
                      <IconCancel />
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={
                        busy ||
                        (!manualCustomer.name.trim() &&
                          !manualCustomer.phone.trim() &&
                          !manualCustomer.email.trim() &&
                          !manualVehicle.year.trim() &&
                          !manualVehicle.make.trim() &&
                          !manualVehicle.model.trim() &&
                          !manualVehicle.mileage.trim() &&
                          !manualVehicle.vin.trim())
                      }
                      className="btn-primary inline-flex items-center justify-center gap-1.5 px-3.5 py-1.5 text-sm disabled:opacity-60"
                    >
                      {busy ? (
                        "Saving…"
                      ) : (
                        <>
                          <IconSave />
                          Save
                        </>
                      )}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        setStep("source");
                        setPrimaryGroup(null);
                        setFileDragOver(false);
                      }}
                      className={`btn-ghost inline-flex items-center justify-center gap-1.5 ${
                        FILE_SOURCES.has(source) ? "px-3.5 py-1.5 text-sm" : "px-4 py-2 text-sm"
                      }`}
                    >
                      Back
                    </button>
                    <button
                      type="submit"
                      disabled={
                        busy ||
                        (selectedSource.requires_upload &&
                          !file &&
                          !(source === "ocr" && ocrText.trim()))
                      }
                      className={`btn-primary inline-flex items-center justify-center gap-1.5 text-sm disabled:opacity-60 ${
                        FILE_SOURCES.has(source) ? "px-3.5 py-1.5" : "px-5 py-2.5"
                      }`}
                    >
                      {busy ? "Starting…" : "Start import"}
                      {!busy ? <IconContinue /> : null}
                    </button>
                  </>
                )}
              </div>
            </form>
          </div>,
          document.body,
        )}

      {step === "progress" && (
        <section className="surface-panel relative max-w-xl shrink-0 overflow-hidden p-6">
          <div
            className="pointer-events-none absolute -right-8 -top-10 h-32 w-32 rounded-full bg-[radial-gradient(circle,rgba(240,90,36,0.18),transparent_70%)]"
            aria-hidden
          />
          <p className="section-label">Import</p>
          <h2 className="font-display mt-1.5 text-lg font-semibold tracking-tight">
            Import in progress
          </h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            {job?.progress.message || (busy ? "Starting import…" : "Working…")}
          </p>
          <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-[var(--background)] ring-1 ring-[var(--line)]">
            <div
              className="h-full rounded-full bg-[linear-gradient(90deg,var(--accent),var(--signal))] transition-all duration-500"
              style={{ width: `${job?.progress.percent ?? (busy ? 5 : 0)}%` }}
            />
          </div>
          <p className="mt-2 text-xs font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
            {job ? `${job.progress.stage} · ${job.progress.percent}%` : "uploading · …"}
          </p>
        </section>
      )}

      {step === "duplicates" && job && (
        <section className="min-w-0 shrink-0 space-y-4">
          <div className="min-w-0">
            <h2 className="font-display text-lg font-semibold tracking-tight">
              Resolve duplicates
            </h2>
            <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-[var(--muted)]">
              These records look similar to ones you already have. Compare both sides, then choose
              how to handle each before applying.
            </p>
          </div>
          <div className="min-w-0 space-y-3">
            {job.duplicates
              .filter((d) => !d.resolved)
              .map((d) => (
                <DuplicateCard
                  key={d.id}
                  dup={d}
                  action={resolutions[d.id] ?? d.suggested_action}
                  onChange={(action) => setResolutions((prev) => ({ ...prev, [d.id]: action }))}
                />
              ))}
          </div>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submitResolutions()}
            className="btn-primary inline-flex items-center justify-center gap-1.5 px-5 py-2.5 text-sm disabled:opacity-60"
          >
            {!busy ? <IconApply /> : null}
            {busy ? "Applying…" : "Apply"}
          </button>
        </section>
      )}

      {step === "report" && job && (
        <section className="shrink-0 space-y-4">
          <div className="surface-panel space-y-5 p-5 sm:p-6">
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status={job.status} />
              {job.source ? (
                <span className="text-sm capitalize text-[var(--muted)]">{job.source}</span>
              ) : null}
            </div>
            {job.error && (
              <p className="rounded-xl border border-red-200/80 bg-red-50 px-3 py-2 text-sm text-red-700">
                {job.error}
              </p>
            )}
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Customers imported" value={entityImported(job, "customer")} />
              <StatCard label="Vehicles imported" value={entityImported(job, "vehicle")} />
              <StatCard label="Repair records" value={entityImported(job, "repair_history")} />
              <StatCard label="Duplicates resolved" value={duplicatesResolved(job)} />
            </div>
            {job.report && (
              <>
                <p className="text-sm text-[var(--muted)]">
                  Duration {job.report.duration_ms}ms · Pending duplicates{" "}
                  {job.report.duplicates_pending}
                </p>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.entries(job.report.entity_counts).map(([kind, c]) => (
                    <div
                      key={kind}
                      className="rounded-xl border border-[var(--line)] bg-[var(--background)]/40 px-3.5 py-3"
                    >
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                        {kind}
                      </p>
                      <p className="font-display mt-1 text-lg font-semibold tracking-tight">
                        {c.imported}{" "}
                        <span className="text-sm font-medium text-[var(--muted)]">imported</span>
                      </p>
                      <p className="mt-1 text-xs text-[var(--muted)]">
                        merged {c.merged} · skipped {c.skipped} · failed {c.failed}
                      </p>
                    </div>
                  ))}
                </div>
                {job.report.warnings.length > 0 && (
                  <ul className="list-disc space-y-1 rounded-xl border border-amber-200/70 bg-amber-50/80 px-5 py-3 pl-8 text-sm text-amber-900">
                    {job.report.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
            {job.validation_issues.length > 0 && (
              <div className="space-y-2 rounded-xl border border-[var(--line)] bg-[var(--background)]/40 p-4">
                <p className="text-sm font-semibold">Validation issues</p>
                {job.validation_issues.map((issue) => (
                  <p key={issue.id} className="text-xs text-[var(--muted)]">
                    [{issue.severity}] {issue.code}: {issue.message}
                  </p>
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      <section className="flex min-h-0 flex-1 flex-col gap-3">
        <h2 className="font-display flex shrink-0 items-center gap-2 text-lg font-semibold tracking-tight">
          <IconHistory className="h-5 w-5 text-[var(--muted)]" />
          History
        </h2>
        <ul className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain rounded-[var(--radius)] border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)] [-webkit-overflow-scrolling:touch]">
          {jobs.map((j) => {
            const selected = job?.id === j.id;
            return (
              <li key={j.id}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => void openRecentJob(j)}
                  className={`flex w-full items-start gap-3 border-t border-[var(--line)] px-3.5 py-3 text-left transition-colors first:border-t-0 ${
                    selected
                      ? "border-l-2 border-l-[var(--accent)] bg-[var(--accent-soft)] pl-[calc(0.875rem-2px)]"
                      : "border-l-2 border-l-transparent hover:bg-[var(--background)]"
                  }`}
                >
                  <span
                    className={`mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${
                      selected
                        ? "bg-[var(--accent)] text-white"
                        : "bg-[var(--background)] text-[var(--foreground)] ring-1 ring-[var(--line)]"
                    }`}
                  >
                    <JobSourceIcon source={j.source} className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
                      <span
                        className={`truncate text-sm capitalize ${
                          selected ? "font-semibold text-[var(--ink)]" : "font-medium"
                        }`}
                      >
                        {j.source}
                      </span>
                      <StatusBadge status={j.status} />
                    </div>
                    <div className="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs text-[var(--muted)]">
                      <span className="min-w-0 break-words tabular-nums">{jobCountsSummary(j)}</span>
                      <span className="shrink-0 whitespace-nowrap">{formatJobCreated(j.created_at)}</span>
                    </div>
                  </div>
                </button>
              </li>
            );
          })}
          {jobs.length === 0 && (
            <li className="px-3.5 py-10 text-center text-sm text-[var(--muted)]">
              No imports yet — start with a spreadsheet or manual entry above.
            </li>
          )}
        </ul>
      </section>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--background)]/40 px-3.5 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        {label}
      </p>
      <p className="font-display mt-1 text-2xl font-semibold tracking-tight tabular-nums">
        {value}
      </p>
    </div>
  );
}

function humanizeKey(key: string): string {
  return FIELD_LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatSnapshotValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "—";
  if (typeof value === "string") {
    const t = value.trim();
    return t || "—";
  }
  return String(value);
}

function snapshotFieldOrder(entityKind: string, snap: Record<string, unknown>): string[] {
  const preferred =
    entityKind === "vehicle"
      ? VEHICLE_FIELD_ORDER
      : entityKind === "customer"
        ? CUSTOMER_FIELD_ORDER
        : Object.keys(FIELD_LABELS);
  const keys = new Set([...preferred, ...Object.keys(snap)]);
  return [...keys].filter((k) => {
    const v = snap[k];
    return v != null && v !== "";
  });
}

function SnapshotPanel({
  title,
  subtitle,
  entityKind,
  snap,
  highlightKey,
}: {
  title: string;
  subtitle?: string;
  entityKind: string;
  snap: Record<string, unknown>;
  highlightKey?: string;
}) {
  const fields = snapshotFieldOrder(entityKind, snap);
  return (
    <div className="min-w-0 rounded-xl border border-[var(--line)] bg-[var(--background)]/35 p-3.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        {title}
      </p>
      {subtitle ? <p className="mt-0.5 text-xs text-[var(--muted)]">{subtitle}</p> : null}
      {fields.length === 0 ? (
        <p className="mt-2 text-sm text-[var(--muted)]">No details available</p>
      ) : (
        <dl className="mt-2.5 min-w-0 space-y-1.5">
          {fields.map((key) => {
            const highlighted = highlightKey === key;
            return (
              <div key={key} className="grid min-w-0 grid-cols-[minmax(4.5rem,6.5rem)_minmax(0,1fr)] gap-2 text-sm">
                <dt className="text-[var(--muted)]">{humanizeKey(key)}</dt>
                <dd
                  className={`min-w-0 break-words [overflow-wrap:anywhere] ${
                    highlighted ? "font-semibold text-[var(--accent)]" : ""
                  }`}
                >
                  {formatSnapshotValue(snap[key])}
                </dd>
              </div>
            );
          })}
        </dl>
      )}
    </div>
  );
}

function DuplicateCard({
  dup,
  action,
  onChange,
}: {
  dup: DuplicateCandidate;
  action: string;
  onChange: (action: string) => void;
}) {
  const entityLabel = ENTITY_LABELS[dup.entity_kind] ?? humanizeKey(dup.entity_kind);
  const matchLabel = MATCH_LABELS[dup.match_type] ?? humanizeKey(dup.match_type);
  const confidence = Math.round(dup.confidence * 100);
  const headline =
    dup.entity_kind === "customer"
      ? formatSnapshotValue(dup.incoming_snapshot.name)
      : dup.entity_kind === "vehicle"
        ? [dup.incoming_snapshot.year, dup.incoming_snapshot.make, dup.incoming_snapshot.model]
            .map(formatSnapshotValue)
            .filter((v) => v !== "—")
            .join(" ") || formatSnapshotValue(dup.incoming_snapshot.vin)
        : entityLabel;

  return (
    <div className="surface-panel min-w-0 p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <p className="font-display break-words text-sm font-semibold tracking-tight [overflow-wrap:anywhere]">
            Possible duplicate {entityLabel.toLowerCase()}
            {headline !== "—" ? `: ${headline}` : ""}
          </p>
          <p className="mt-1 break-words text-xs text-[var(--muted)]">
            Matched by {matchLabel} · {confidence}% confidence
          </p>
        </div>
        <select
          className="w-full max-w-full shrink-0 rounded-xl border border-[var(--line)] bg-[var(--background)]/40 px-3 py-2 text-sm sm:w-auto"
          value={action}
          onChange={(e) => onChange(e.target.value)}
          aria-label={`How to resolve duplicate for ${headline}`}
        >
          {MERGE_ACTIONS.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </select>
      </div>
      <div className="mt-4 grid min-w-0 gap-3 sm:grid-cols-2">
        <SnapshotPanel
          title="Importing"
          subtitle="From this import"
          entityKind={dup.entity_kind}
          snap={dup.incoming_snapshot}
          highlightKey={dup.match_type}
        />
        <SnapshotPanel
          title="Already saved"
          subtitle={dup.existing_ref ? "In your shop records" : "Also in this import"}
          entityKind={dup.entity_kind}
          snap={dup.existing_snapshot}
          highlightKey={dup.match_type}
        />
      </div>
    </div>
  );
}
