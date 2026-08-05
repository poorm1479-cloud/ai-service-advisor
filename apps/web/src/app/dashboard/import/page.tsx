"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
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
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

type WizardStep = "source" | "configure" | "progress" | "duplicates" | "report";
type DisplayStep = "Upload" | "Review" | "Import" | "Complete";

const DISPLAY_STEPS: DisplayStep[] = ["Upload", "Review", "Import", "Complete"];

const FILE_SOURCES = new Set(["csv", "excel"]);

const MERGE_ACTIONS = [
  { value: "merge", label: "Merge" },
  { value: "keep_existing", label: "Keep existing" },
  { value: "keep_incoming", label: "Keep incoming" },
  { value: "skip", label: "Skip" },
];

function displayStepFor(step: WizardStep): DisplayStep {
  if (step === "source") return "Upload";
  if (step === "configure") return "Review";
  if (step === "progress" || step === "duplicates") return "Import";
  return "Complete";
}

function entityImported(job: ImportJob, kind: string): number {
  return job.report?.entity_counts?.[kind]?.imported ?? job.batch_counts?.[kind] ?? 0;
}

function duplicatesResolved(job: ImportJob): number {
  if (job.report) return job.report.duplicates_resolved;
  return job.duplicates.filter((d) => d.resolved).length;
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
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
      />
    </label>
  );
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

  const refreshJobs = useCallback(async () => {
    setJobs(await listImportJobs());
  }, []);

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
        setManualCustomer(EMPTY_CUSTOMER);
        setManualVehicle(EMPTY_VEHICLE);
        setStep("duplicates");
        return;
      }

      if (ran.status === "failed") {
        setError(formatManualSaveResult(ran));
        return;
      }

      setSuccess(formatManualSaveResult(ran));
      setManualCustomer(EMPTY_CUSTOMER);
      setManualVehicle(EMPTY_VEHICLE);
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
      // Spreadsheet uploads: pick connector from file extension (CSV vs Excel).
      if (FILE_SOURCES.has(source) || primaryGroup === "file") {
        if (!file) throw new Error("Upload a CSV or Excel file to continue");
        const inferred = inferFileImportSource(file.name);
        if (!inferred) {
          throw new Error("Unsupported file type. Use .csv or .xlsx");
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
        setManualCustomer(EMPTY_CUSTOMER);
        setManualVehicle(EMPTY_VEHICLE);
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

  function resetWizard() {
    setStep("source");
    setSource("");
    setFile(null);
    setJob(null);
    setError(null);
    setSuccess(null);
    setManualCustomer(EMPTY_CUSTOMER);
    setManualVehicle(EMPTY_VEHICLE);
    setPrimaryGroup(null);
  }

  if (!authLoading && session && session.role !== "owner") {
    return (
      <div className="space-y-6">
        <h1 className="page-title">Import</h1>
        <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Only shop owners can import data.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Import</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Bring in shop history so AI can advise with real customer and vehicle context
          </p>
        </div>
        {step !== "source" && (
          <button
            type="button"
            onClick={resetWizard}
            className="rounded-md border border-[var(--line)] px-3 py-2 text-sm text-[var(--muted)]"
          >
            New import
          </button>
        )}
      </div>

      <ol className="flex flex-wrap gap-2 text-xs uppercase tracking-[0.12em] text-[var(--muted)]">
        {DISPLAY_STEPS.map((label) => (
          <li
            key={label}
            className={`rounded-md px-2 py-1 ${
              activeDisplayStep === label ? "bg-[var(--accent-soft)] text-[var(--accent)]" : ""
            }`}
          >
            {label}
          </li>
        ))}
      </ol>

      {error && (
        <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {success && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {success}
        </p>
      )}

      {step === "source" && (
        <section className="space-y-4">
          <aside className="max-w-2xl rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3">
            <h2 className="text-sm font-medium">AI Import Assistant</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">While importing, AI will:</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-[var(--muted)]">
              <li>detect customers</li>
              <li>match vehicles</li>
              <li>build repair history</li>
              <li>create memory</li>
            </ul>
          </aside>

          <div>
            <h2 className="text-sm font-medium">Choose how to import</h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => {
                  setPrimaryGroup("file");
                  setSource(fileSources[0]?.source ?? "csv");
                }}
                className={`rounded-md border bg-[var(--panel)] px-4 py-3 text-left hover:border-[var(--accent)] ${
                  primaryGroup === "file" ? "border-[var(--accent)]" : "border-[var(--line)]"
                }`}
              >
                <p className="text-sm font-medium">CSV / Excel</p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Spreadsheet exports from your shop
                </p>
              </button>

              {manualSource && (
              <button
                type="button"
                onClick={() => {
                  setSuccess(null);
                  setError(null);
                  selectSource("manual");
                }}
                className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-4 py-3 text-left hover:border-[var(--accent)]"
              >
                <p className="text-sm font-medium">Manual Entry</p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Enter a customer and vehicle with simple forms
                </p>
              </button>
              )}
            </div>
          </div>

          {primaryGroup === "file" && (
            <div className="max-w-xl space-y-3 rounded-md border border-[var(--line)] bg-[var(--panel)] p-4">
              <p className="text-sm font-medium">Select file type</p>
              <div className="flex flex-wrap gap-2">
                {fileSources.map((s) => (
                  <button
                    key={s.source}
                    type="button"
                    onClick={() => setSource(s.source)}
                    className={`rounded-md border px-3 py-2 text-sm ${
                      source === s.source
                        ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                        : "border-[var(--line)]"
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <button
                type="button"
                disabled={!source || !FILE_SOURCES.has(source)}
                onClick={() => setStep("configure")}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                Continue
              </button>
            </div>
          )}
        </section>
      )}

      {step === "configure" && selectedSource && (
        <form onSubmit={startImport} className="max-w-2xl space-y-4 rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
          <h2 className="text-sm font-medium">
            {source === "manual" ? "Manual Entry" : `Review · ${selectedSource.label}`}
          </h2>
          <p className="text-sm text-[var(--muted)]">
            {source === "manual"
              ? "Enter a customer and/or vehicle, then save. The form stays open for the next entry."
              : "Confirm source settings, then start import. Validation and duplicate detection run next."}
          </p>

          {selectedSource.requires_upload && (
            <div className="space-y-3">
              <input
                type="file"
                accept={
                  FILE_SOURCES.has(source)
                    ? ".csv,.tsv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    : source === "pdf"
                      ? ".pdf,application/pdf"
                      : "*/*"
                }
                onChange={(e) => {
                  const next = e.target.files?.[0] ?? null;
                  setFile(next);
                  if (next && FILE_SOURCES.has(source)) {
                    const inferred = inferFileImportSource(next.name);
                    if (inferred) setSource(inferred);
                  }
                }}
                className="block w-full text-sm"
              />
              {FILE_SOURCES.has(source) && (
                <p className="text-xs text-[var(--muted)]">
                  Accepts CSV or Excel (.xlsx). Connector is chosen from the file type
                  {file ? ` · using ${source.toUpperCase()}` : ""}.
                </p>
              )}
              {(source === "ocr" || source === "pdf") && (
                <textarea
                  className="min-h-28 w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 text-sm"
                  placeholder="OCR / document text (optional for PDF; required for OCR without file)"
                  value={ocrText}
                  onChange={(e) => setOcrText(e.target.value)}
                />
              )}
            </div>
          )}

          {source === "manual" && (
            <div className="space-y-5">
              <div className="space-y-3">
                <h3 className="text-sm font-medium">Customer</h3>
                <div className="grid gap-3 sm:grid-cols-2">
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

              <div className="space-y-3">
                <h3 className="text-sm font-medium">Vehicle</h3>
                <div className="grid gap-3 sm:grid-cols-2">
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
                  <div className="sm:col-span-2">
                    <ManualField
                      label="VIN (optional)"
                      value={manualVehicle.vin}
                      onChange={(vin) => setManualVehicle((v) => ({ ...v, vin }))}
                      placeholder="17-character VIN"
                      autoComplete="off"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setStep("source");
                setPrimaryGroup(null);
              }}
              className="rounded-md border border-[var(--line)] px-4 py-2 text-sm"
            >
              Back
            </button>
            <button
              type="submit"
              disabled={
                busy ||
                (selectedSource.requires_upload &&
                  !file &&
                  !(source === "ocr" && ocrText.trim())) ||
                (source === "manual" &&
                  !manualCustomer.name.trim() &&
                  !manualCustomer.phone.trim() &&
                  !manualCustomer.email.trim() &&
                  !manualVehicle.year.trim() &&
                  !manualVehicle.make.trim() &&
                  !manualVehicle.model.trim() &&
                  !manualVehicle.mileage.trim() &&
                  !manualVehicle.vin.trim())
              }
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            >
              {source === "manual"
                ? busy
                  ? "Saving…"
                  : "Save"
                : busy
                  ? "Starting…"
                  : "Start import"}
            </button>
          </div>
        </form>
      )}

      {step === "progress" && (
        <section className="max-w-xl space-y-3 rounded-md border border-[var(--line)] bg-[var(--panel)] p-5">
          <h2 className="text-sm font-medium">Import in progress</h2>
          <p className="text-sm text-[var(--muted)]">
            {job?.progress.message || (busy ? "Starting import…" : "Working…")}
          </p>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--line)]">
            <div
              className="h-full bg-[var(--accent)] transition-all"
              style={{ width: `${job?.progress.percent ?? (busy ? 5 : 0)}%` }}
            />
          </div>
          <p className="text-xs text-[var(--muted)]">
            {job ? `${job.progress.stage} · ${job.progress.percent}%` : "uploading · …"}
          </p>
        </section>
      )}

      {step === "duplicates" && job && (
        <section className="space-y-4">
          <h2 className="text-sm font-medium">Import · Resolve duplicates</h2>
          <p className="text-sm text-[var(--muted)]">
            AI detected potential duplicates. Choose merge actions before applying.
          </p>
          <div className="space-y-3">
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
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {busy ? "Applying…" : "Apply resolutions"}
          </button>
        </section>
      )}

      {step === "report" && job && (
        <section className="space-y-4">
          <h2 className="text-sm font-medium">Complete</h2>
          <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-5 text-sm">
            <p>
              Status: <span className="font-medium">{job.status}</span>
            </p>
            {job.error && <p className="mt-2 text-red-600">{job.error}</p>}
            {job.report && (
              <>
                <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <StatCard label="Customers imported" value={entityImported(job, "customer")} />
                  <StatCard label="Vehicles imported" value={entityImported(job, "vehicle")} />
                  <StatCard label="Repair records" value={entityImported(job, "repair_history")} />
                  <StatCard label="Duplicates resolved" value={job.report.duplicates_resolved} />
                </div>
                <p className="mt-3 text-[var(--muted)]">
                  Duration {job.report.duration_ms}ms · Pending duplicates{" "}
                  {job.report.duplicates_pending}
                </p>
                <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {Object.entries(job.report.entity_counts).map(([kind, c]) => (
                    <div key={kind} className="rounded-md border border-[var(--line)] px-3 py-2">
                      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{kind}</p>
                      <p className="mt-1 font-medium">{c.imported} imported</p>
                      <p className="text-xs text-[var(--muted)]">
                        merged {c.merged} · skipped {c.skipped} · failed {c.failed}
                      </p>
                    </div>
                  ))}
                </div>
                {job.report.warnings.length > 0 && (
                  <ul className="mt-4 list-disc space-y-1 pl-5 text-[var(--muted)]">
                    {job.report.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                )}
                {job.validation_issues.length > 0 && (
                  <div className="mt-4 space-y-2">
                    <p className="font-medium">Validation issues</p>
                    {job.validation_issues.map((issue) => (
                      <p key={issue.id} className="text-xs text-[var(--muted)]">
                        [{issue.severity}] {issue.code}: {issue.message}
                      </p>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium">Recent jobs</h2>
        <div className="overflow-x-auto rounded-md border border-[var(--line)]">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-[var(--panel)] text-xs uppercase tracking-wide text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Customers</th>
                <th className="px-3 py-2">Vehicles</th>
                <th className="px-3 py-2">Repairs</th>
                <th className="px-3 py-2">Duplicates</th>
                <th className="px-3 py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr
                  key={j.id}
                  className="cursor-pointer border-t border-[var(--line)] hover:bg-[var(--accent-soft)]"
                  onClick={() => {
                    setJob(j);
                    setStep(
                      j.status === "awaiting_resolution"
                        ? "duplicates"
                        : j.status === "completed" || j.status === "failed"
                          ? "report"
                          : "progress",
                    );
                  }}
                >
                  <td className="px-3 py-2">{j.source}</td>
                  <td className="px-3 py-2">{j.status}</td>
                  <td className="px-3 py-2">{entityImported(j, "customer")}</td>
                  <td className="px-3 py-2">{entityImported(j, "vehicle")}</td>
                  <td className="px-3 py-2">{entityImported(j, "repair_history")}</td>
                  <td className="px-3 py-2">{duplicatesResolved(j)}</td>
                  <td className="px-3 py-2 text-[var(--muted)]">
                    {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-3 py-6 text-[var(--muted)]">
                    No imports yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-[var(--line)] px-3 py-2">
      <p className="text-xs uppercase tracking-wide text-[var(--muted)]">{label}</p>
      <p className="mt-1 text-lg font-medium">{value}</p>
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
  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--panel)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">
          {dup.entity_kind} · {dup.match_type} · {(dup.confidence * 100).toFixed(0)}%
        </p>
        <select
          className="rounded-md border border-[var(--line)] bg-transparent px-2 py-1 text-sm"
          value={action}
          onChange={(e) => onChange(e.target.value)}
        >
          {MERGE_ACTIONS.map((a) => (
            <option key={a.value} value={a.value}>
              {a.label}
            </option>
          ))}
        </select>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 text-xs">
        <pre className="overflow-auto rounded-md border border-[var(--line)] p-2">
          {JSON.stringify(dup.incoming_snapshot, null, 2)}
        </pre>
        <pre className="overflow-auto rounded-md border border-[var(--line)] p-2">
          {JSON.stringify(dup.existing_snapshot, null, 2)}
        </pre>
      </div>
    </div>
  );
}
