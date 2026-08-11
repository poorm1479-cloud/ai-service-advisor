"use client";

import { FormEvent, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth } from "@/lib/auth";
import {
  ServiceInput,
  ShopService,
  createShopService,
  deleteShopService,
  formatPrice,
  getSetupState,
  listShopServices,
  updateShopService,
} from "@/lib/shopSetup";

type ServiceFormState = Omit<ServiceInput, "duration_minutes"> & {
  /** Empty string while the user clears the field (avoid flashing 0). */
  duration_minutes: number | "";
};

const DEFAULT_FORM: ServiceFormState = {
  name: "",
  category: "maintenance",
  duration_minutes: 60,
  price: "0.00",
  skill: "general",
  bay: "general",
  active: true,
};

const DURATION_PRESETS = [30, 60, 90, 120] as const;

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function IconWrench({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  );
}

function IconPlus({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function IconWrenchPlus({ className = "h-4 w-4" }: { className?: string }) {
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
      {/* Center wrench and + on the same midline (y=11), matching UserPlus/CalendarPlus */}
      <g transform="translate(7, 11) scale(0.55) translate(-12, -12)">
        <path
          d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"
          strokeWidth="3.2"
        />
      </g>
      <path d="M19 8v6M16 11h6" />
    </svg>
  );
}

function IconClock({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </svg>
  );
}

function IconTag({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M12 2H2v10l9.29 9.29a1 1 0 0 0 1.41 0l8.59-8.59a1 1 0 0 0 0-1.41L12 2Z" />
      <circle cx="7" cy="7" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

function IconSave({ className = "h-3.5 w-3.5" }: { className?: string }) {
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

function IconX({ className = "h-3.5 w-3.5" }: { className?: string }) {
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

function IconPencil({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

function IconTrash({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

const fieldClass =
  "w-full rounded-lg border border-[var(--line)] bg-white px-3 py-2 text-sm text-[var(--ink)] outline-none transition placeholder:text-[var(--muted)]/70 focus:border-[var(--accent)]/40 focus:ring-2 focus:ring-[var(--accent)]/25";

export function ServicesPanel({
  embedded = false,
  editing = true,
}: {
  embedded?: boolean;
  /** When embedded under Shop, driven by the Shop tab Change button. */
  editing?: boolean;
}) {
  const { session, loading: authLoading } = useAuth();
  const isOwner = session?.role === "owner";

  const [services, setServices] = useState<ShopService[]>([]);
  const [categories, setCategories] = useState<string[]>(["other"]);
  const [skills, setSkills] = useState<string[]>(["general"]);
  const [bayTypes, setBayTypes] = useState<string[]>(["general"]);
  const [form, setForm] = useState<ServiceFormState>(DEFAULT_FORM);
  const [initialForm, setInitialForm] = useState<ServiceFormState | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ShopService | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  /** Client-only: portal modals past overflow-hidden settings shells. */
  const [portalReady, setPortalReady] = useState(false);
  const canEdit = isOwner && editing;

  useEffect(() => {
    setPortalReady(true);
  }, []);

  async function reload() {
    const [list, state] = await Promise.all([listShopServices(), getSetupState()]);
    setServices(list);
    setCategories(state.meta.categories);
    setSkills(state.meta.skills);
    setBayTypes(state.meta.bay_types);
  }

  useEffect(() => {
    if (authLoading || !session) return;
    let cancelled = false;
    setLoading(true);
    reload()
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load services");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, session]);

  function resetForm() {
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setInitialForm(null);
    setFormOpen(false);
    setError(null);
  }

  // Shop tab Cancel / leaving edit: close service modals.
  useEffect(() => {
    if (editing) return;
    setDeleteTarget(null);
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setInitialForm(null);
    setFormOpen(false);
    setError(null);
    setSuccess(null);
  }, [editing]);

  useEffect(() => {
    if (!formOpen && !deleteTarget) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (saving || deleting) return;
      e.preventDefault();
      if (deleteTarget) {
        setDeleteTarget(null);
        return;
      }
      setEditingId(null);
      setForm(DEFAULT_FORM);
      setInitialForm(null);
      setFormOpen(false);
      setError(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [formOpen, deleteTarget, saving, deleting]);

  function openAddForm() {
    if (!canEdit) return;
    setEditingId(null);
    setForm({
      ...DEFAULT_FORM,
      category: categories[0] ?? "maintenance",
      skill: skills[0] ?? "general",
      bay: bayTypes[0] ?? "general",
    });
    setInitialForm(null);
    setFormOpen(true);
    setSuccess(null);
    setError(null);
  }

  function startEdit(svc: ShopService) {
    if (!canEdit) return;
    const next: ServiceFormState = {
      name: svc.name,
      category: svc.category,
      duration_minutes: svc.duration_minutes,
      price: formatPrice(svc.price),
      skill: svc.skill,
      bay: svc.bay,
      active: svc.active,
    };
    setEditingId(svc.id);
    setForm(next);
    setInitialForm(next);
    setFormOpen(true);
    setSuccess(null);
    setError(null);
  }

  function isFormDirty(): boolean {
    if (!editingId || !initialForm) return true;
    return (
      form.name.trim() !== initialForm.name.trim() ||
      form.category !== initialForm.category ||
      Number(form.duration_minutes) !== Number(initialForm.duration_minutes) ||
      Number(form.price) !== Number(initialForm.price) ||
      form.skill !== initialForm.skill ||
      form.bay !== initialForm.bay ||
      form.active !== initialForm.active
    );
  }

  function isDuplicateName(name: string, excludeId?: string | null): boolean {
    const normalized = name.trim().toLowerCase();
    if (!normalized) return false;
    return services.some(
      (s) => s.name.trim().toLowerCase() === normalized && s.id !== excludeId,
    );
  }

  const durationMinutes =
    form.duration_minutes === "" ? NaN : Number(form.duration_minutes);
  const canSave =
    !!form.name.trim() &&
    Number.isFinite(durationMinutes) &&
    durationMinutes >= 5 &&
    !saving &&
    (!editingId || isFormDirty());

  const previewPrice = Number(form.price);
  const previewPriceLabel = Number.isFinite(previewPrice)
    ? `$${formatPrice(previewPrice)}`
    : "$—";

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canEdit || !canSave) return;
    const name = form.name.trim();
    setError(null);
    setSuccess(null);
    if (isDuplicateName(name, editingId)) {
      setError("A service with this name already exists.");
      return;
    }
    setSaving(true);
    const payload: ServiceInput = {
      ...form,
      name,
      duration_minutes: durationMinutes,
      price: Number(form.price),
    };
    try {
      if (editingId) {
        await updateShopService(editingId, payload);
        setSuccess("Service updated.");
      } else {
        await createShopService(payload);
        setSuccess("Service created.");
      }
      resetForm();
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save service");
    } finally {
      setSaving(false);
    }
  }

  function openDeleteConfirm(svc: ShopService) {
    if (!canEdit) return;
    setDeleteTarget(svc);
    setError(null);
    setSuccess(null);
  }

  function closeDeleteConfirm() {
    if (deleting) return;
    setDeleteTarget(null);
  }

  async function onConfirmDelete() {
    if (!canEdit || !deleteTarget) return;
    setDeleting(true);
    setError(null);
    setSuccess(null);
    try {
      await deleteShopService(deleteTarget.id);
      if (editingId === deleteTarget.id) resetForm();
      setDeleteTarget(null);
      setSuccess("Service deleted.");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete service");
    } finally {
      setDeleting(false);
    }
  }

  async function toggleActive(svc: ShopService) {
    if (!canEdit) return;
    setError(null);
    try {
      await updateShopService(svc.id, { active: !svc.active });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update service");
    }
  }

  if (authLoading || !session) {
    return <p className="text-sm text-[var(--muted)]">Loading…</p>;
  }

  const catalogBody = (
    <>
      {loading ? (
        <div className="flex items-center gap-3 py-8 text-sm text-[var(--muted)]">
          <span className="h-4 w-4 animate-pulse rounded-full bg-[var(--accent)]/40" />
          Loading catalog…
        </div>
      ) : services.length === 0 ? (
        <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
          <span className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--accent-soft)] to-white text-[var(--accent)] shadow-sm ring-1 ring-[var(--accent)]/15">
            <IconWrench className="h-6 w-6" />
          </span>
          <p className="font-display mt-4 text-base font-semibold tracking-tight text-[var(--ink)]">
            No services yet
          </p>
          <p className="mt-1.5 max-w-sm text-sm text-[var(--muted)]">
            Build your catalog so the AI and staff can quote, schedule, and book the right work.
          </p>
          {canEdit && (
            <button
              type="button"
              onClick={openAddForm}
              className="btn-primary mt-5 inline-flex items-center gap-1.5 px-4 py-2 text-xs"
            >
              <IconPlus className="h-3.5 w-3.5" />
              Add your first service
            </button>
          )}
        </div>
      ) : (
        <ul className="divide-y divide-[var(--line)]">
          {services.map((svc) => (
            <li
              key={svc.id}
              className={`group flex flex-col gap-3 py-3.5 first:pt-1 last:pb-1 sm:flex-row sm:items-center sm:justify-between ${
                svc.active ? "" : "opacity-70"
              }`}
            >
              <div className="min-w-0 flex items-start gap-3">
                <span
                  className={`mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ring-1 ${
                    svc.active
                      ? "bg-[var(--accent-soft)] text-[var(--accent)] ring-[var(--accent)]/15"
                      : "bg-black/[0.04] text-[var(--muted)] ring-black/5"
                  }`}
                >
                  <IconWrench className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-semibold tracking-tight text-[var(--ink)]">
                      {svc.name}
                    </p>
                    <span className="rounded-full bg-black/[0.04] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)] ring-1 ring-inset ring-black/5">
                      {titleCase(svc.category)}
                    </span>
                    {!svc.active && (
                      <span className="rounded-full bg-black/[0.04] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                        Inactive
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--muted)]">
                    <span className="inline-flex items-center gap-1">
                      <IconClock className="h-3 w-3" />
                      {svc.duration_minutes} min
                    </span>
                    <span className="font-medium tabular-nums text-[var(--ink)]">
                      ${formatPrice(svc.price)}
                    </span>
                    <span>{titleCase(svc.skill)}</span>
                    <span className="text-[var(--line)]">·</span>
                    <span>{titleCase(svc.bay)} bay</span>
                  </div>
                </div>
              </div>

              <div className="flex shrink-0 items-center gap-2 self-end sm:self-center">
                {canEdit ? (
                  <>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={svc.active}
                      aria-label={`${svc.name} ${svc.active ? "active" : "inactive"}`}
                      onClick={() => void toggleActive(svc)}
                      className="inline-flex items-center gap-2 rounded-full px-1 py-1 transition hover:opacity-90"
                    >
                      <span
                        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                          svc.active
                            ? "bg-[var(--accent)] shadow-sm shadow-[var(--accent-glow)]"
                            : "bg-black/15"
                        }`}
                      >
                        <span
                          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all duration-200 ${
                            svc.active ? "left-[1.125rem]" : "left-0.5"
                          }`}
                        />
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => startEdit(svc)}
                      className="btn-ghost inline-flex items-center gap-1 px-2.5 py-1.5 text-xs"
                    >
                      <IconPencil className="h-3.5 w-3.5" />
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => openDeleteConfirm(svc)}
                      className="inline-flex items-center gap-1 rounded-full px-2.5 py-1.5 text-xs font-semibold text-red-600 transition hover:bg-red-50"
                    >
                      <IconTrash className="h-3.5 w-3.5" />
                      Delete
                    </button>
                  </>
                ) : (
                  <span
                    className={`rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${
                      svc.active
                        ? "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-200/80"
                        : "bg-black/[0.04] text-[var(--muted)] ring-1 ring-inset ring-black/5"
                    }`}
                  >
                    {svc.active ? "Active" : "Inactive"}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );

  const modals =
    portalReady &&
    createPortal(
    <>
      {canEdit && deleteTarget && (
        <div
          className="fixed inset-0 z-[100]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-service-title"
          onPointerDown={(e) => e.stopPropagation()}
          onPointerUp={(e) => e.stopPropagation()}
          onPointerCancel={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            tabIndex={-1}
            aria-label="Close delete dialog"
            className="absolute inset-0 cursor-default bg-slate-950/55 backdrop-blur-[2px]"
            disabled={deleting}
            onPointerDown={(e) => {
              if (e.button !== 0) return;
              if (deleting) return;
              e.preventDefault();
              closeDeleteConfirm();
            }}
          />
          <div className="pointer-events-none relative flex h-full items-end justify-center p-4 sm:items-center">
            <div className="pointer-events-auto w-full max-w-sm overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]">
            <div className="relative overflow-hidden border-b border-red-100 bg-gradient-to-br from-red-50 via-white to-white px-4 pb-4 pt-5">
              <div
                className="pointer-events-none absolute -right-8 -top-10 h-32 w-32 rounded-full bg-red-100/70 blur-2xl"
                aria-hidden="true"
              />
              <div className="relative flex items-center gap-3">
                <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-red-600 text-white shadow-lg shadow-red-600/25">
                  <IconTrash className="h-4 w-4" />
                </span>
                <div className="min-w-0">
                  <h2
                    id="delete-service-title"
                    className="text-base font-semibold tracking-tight text-slate-900"
                  >
                    Delete {deleteTarget.name}?
                  </h2>
                </div>
              </div>
            </div>
            <p className="px-4 pt-3.5 text-sm text-[var(--muted)]">
              This service will be removed from the catalog. This cannot be undone.
            </p>
            {error && (
              <p className="mx-4 mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {error}
              </p>
            )}
            <div className="flex flex-wrap justify-end gap-2 px-4 py-3.5">
              <button
                type="button"
                onClick={closeDeleteConfirm}
                disabled={deleting}
                className="btn-ghost px-3.5 py-2 text-sm disabled:opacity-60"
              >
                No
              </button>
              <button
                type="button"
                onClick={() => void onConfirmDelete()}
                disabled={deleting}
                className="inline-flex items-center justify-center rounded-full bg-red-600 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-red-600/20 hover:bg-red-700 disabled:opacity-60"
              >
                {deleting ? "Deleting…" : "Yes"}
              </button>
            </div>
            </div>
          </div>
        </div>
      )}

      {canEdit && formOpen && (
        <div
          className="fixed inset-0 z-[100]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="service-form-title"
          onPointerDown={(e) => e.stopPropagation()}
          onPointerUp={(e) => e.stopPropagation()}
          onPointerCancel={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            tabIndex={-1}
            aria-label="Close service dialog"
            className="absolute inset-0 cursor-default bg-slate-950/55 backdrop-blur-[2px]"
            disabled={saving}
            onPointerDown={(e) => {
              // pointerdown closes more reliably than click on touch (slight
              // movement often suppresses the click event).
              if (e.button !== 0) return;
              if (saving) return;
              e.preventDefault();
              resetForm();
            }}
          />
          <div className="pointer-events-none relative flex h-full items-end justify-center p-4 sm:items-center">
            <div className="pointer-events-auto flex max-h-[min(90dvh,32rem)] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]">
            <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 pb-5 pt-6">
              <div
                className="pointer-events-none absolute right-0 top-0 h-40 w-40 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                aria-hidden="true"
              />
              <div className="relative flex min-w-0 items-center gap-3">
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]">
                  <IconWrench className="h-4 w-4" />
                </span>
                <h2
                  id="service-form-title"
                  className="text-lg font-semibold tracking-tight text-[var(--ink)]"
                >
                  {editingId ? "Edit service" : "Add service"}
                </h2>
              </div>

              <div className="relative mt-3 flex flex-wrap items-center gap-1.5 rounded-lg border border-[var(--line)] bg-white/80 px-2.5 py-1.5 shadow-sm backdrop-blur-sm">
                <IconTag className="h-3 w-3 shrink-0 text-[var(--accent)]" />
                <span className="min-w-0 truncate text-xs font-semibold text-[var(--ink)]">
                  {form.name.trim() || "Untitled service"}
                </span>
                <span className="ml-auto flex flex-wrap items-center gap-1.5 text-[11px] text-[var(--muted)]">
                  <span className="inline-flex items-center gap-1 rounded-full bg-black/[0.04] px-1.5 py-0.5 font-medium ring-1 ring-inset ring-black/5">
                    <IconClock className="h-2.5 w-2.5" />
                    {form.duration_minutes || "—"}m
                  </span>
                  <span className="rounded-full bg-[var(--accent-soft)] px-1.5 py-0.5 font-semibold tabular-nums text-[var(--accent)] ring-1 ring-inset ring-[var(--accent)]/20">
                    {previewPriceLabel}
                  </span>
                </span>
              </div>
            </div>

            {error && (
              <p
                className="mx-4 mt-3 shrink-0 rounded-lg border border-red-200/80 bg-red-50 px-3 py-2 text-xs text-red-700"
                role="alert"
              >
                {error}
              </p>
            )}

            <form
              onSubmit={onSubmit}
              className="asa-scroll flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain"
            >
              <div className="space-y-4 px-4 py-4">
                <div className="space-y-2.5">
                  <label className="block space-y-1">
                    <span className="text-[11px] font-medium text-[var(--muted)]">Service name</span>
                    <input
                      required
                      autoFocus
                      value={form.name}
                      placeholder="e.g. Oil change"
                      onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                      className={fieldClass}
                    />
                  </label>
                  <label className="block space-y-1">
                    <span className="text-[11px] font-medium text-[var(--muted)]">Category</span>
                    <select
                      value={form.category}
                      onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                      className={fieldClass}
                    >
                      {categories.map((c) => (
                        <option key={c} value={c}>
                          {titleCase(c)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <label className="block space-y-1">
                      <span className="text-[11px] font-medium text-[var(--muted)]">
                        Duration (min)
                      </span>
                      <input
                        type="number"
                        min={5}
                        required
                        value={form.duration_minutes}
                        onChange={(e) => {
                          const raw = e.target.value;
                          setForm((f) => ({
                            ...f,
                            duration_minutes: raw === "" ? "" : Number(raw),
                          }));
                        }}
                        className={fieldClass}
                      />
                    </label>
                    <div className="flex flex-wrap gap-1">
                      {DURATION_PRESETS.map((mins) => {
                        const selected = Number(form.duration_minutes) === mins;
                        return (
                          <button
                            key={mins}
                            type="button"
                            onClick={() =>
                              setForm((f) => ({ ...f, duration_minutes: mins }))
                            }
                            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${
                              selected
                                ? "bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]"
                                : "bg-black/[0.04] text-[var(--muted)] ring-1 ring-inset ring-black/5 hover:text-[var(--ink)]"
                            }`}
                          >
                            {mins}m
                          </button>
                        );
                      })}
                    </div>
                  </div>
                  <label className="block space-y-1">
                    <span className="text-[11px] font-medium text-[var(--muted)]">Price</span>
                    <div className="relative">
                      <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-xs font-medium text-[var(--muted)]">
                        $
                      </span>
                      <input
                        type="number"
                        min={0}
                        step="0.01"
                        required
                        value={form.price}
                        onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
                        className={`${fieldClass} pl-6 tabular-nums`}
                      />
                    </div>
                  </label>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block space-y-1">
                    <span className="text-[11px] font-medium text-[var(--muted)]">Skill</span>
                    <select
                      value={form.skill}
                      onChange={(e) => setForm((f) => ({ ...f, skill: e.target.value }))}
                      className={fieldClass}
                    >
                      {skills.map((s) => (
                        <option key={s} value={s}>
                          {titleCase(s)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="block space-y-1">
                    <span className="text-[11px] font-medium text-[var(--muted)]">Bay</span>
                    <select
                      value={form.bay}
                      onChange={(e) => setForm((f) => ({ ...f, bay: e.target.value }))}
                      className={fieldClass}
                    >
                      {bayTypes.map((b) => (
                        <option key={b} value={b}>
                          {titleCase(b)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--line)] bg-gradient-to-br from-white to-[var(--background)]/80 px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[var(--ink)]">Active in catalog</p>
                    <p className="mt-0.5 text-[11px] text-[var(--muted)]">
                      Hidden from booking when off.
                    </p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={form.active}
                    aria-label="Active in catalog"
                    onClick={() => setForm((f) => ({ ...f, active: !f.active }))}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-full px-1 py-1"
                  >
                    <span
                      className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                        form.active
                          ? "bg-[var(--accent)] shadow-sm shadow-[var(--accent-glow)]"
                          : "bg-black/15"
                      }`}
                    >
                      <span
                        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all duration-200 ${
                          form.active ? "left-[1.125rem]" : "left-0.5"
                        }`}
                      />
                    </span>
                    <span
                      className={`min-w-[1.75rem] text-[11px] font-semibold ${
                        form.active ? "text-[var(--ink)]" : "text-[var(--muted)]"
                      }`}
                    >
                      {form.active ? "On" : "Off"}
                    </span>
                  </button>
                </div>
              </div>

              <div className="sticky bottom-0 flex flex-wrap items-center justify-end gap-2 border-t border-[var(--line)] bg-[var(--panel)]/95 px-4 py-3 backdrop-blur-sm">
                <button
                  type="button"
                  onClick={resetForm}
                  className="btn-ghost inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs"
                >
                  <IconX className="h-3.5 w-3.5" />
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!canSave}
                  className="btn-primary inline-flex items-center gap-1.5 px-4 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <IconSave className="h-3.5 w-3.5" />
                  {saving ? "Saving…" : "Save"}
                </button>
              </div>
            </form>
            </div>
          </div>
        </div>
      )}
    </>,
    document.body,
  );

  const addServiceButton =
    canEdit && services.length > 0 ? (
      <button
        type="button"
        onClick={openAddForm}
        aria-label="Add service"
        title="Add service"
        className="btn-primary inline-flex h-10 w-10 shrink-0 items-center justify-center p-0"
      >
        <IconWrenchPlus className="h-5 w-5" />
      </button>
    ) : null;

  if (embedded) {
    return (
      <section className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--ink)]">
              <span className="inline-flex h-6 w-6 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] ring-1 ring-[var(--accent)]/15">
                <IconWrench className="h-3.5 w-3.5" />
              </span>
              Services
              {services.length > 0 && (
                <span className="rounded-full bg-black/[0.04] px-2 py-0.5 text-[10px] font-semibold tabular-nums text-[var(--muted)] ring-1 ring-inset ring-black/5">
                  {services.length}
                </span>
              )}
            </h3>
            <p className="mt-1 text-xs text-[var(--muted)]">
              {!isOwner && "Only the shop owner can change the service catalog. "}
              Add every service your shop provides.
            </p>
          </div>
          {addServiceButton}
        </div>
        {error && !formOpen && !deleteTarget && (
          <p
            className="rounded-xl border border-red-200/80 bg-red-50 px-4 py-3 text-sm text-red-700"
            role="alert"
          >
            {error}
          </p>
        )}
        {success && (
          <p
            className="rounded-xl border border-emerald-200/80 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800"
            role="status"
          >
            {success}
          </p>
        )}
        <div className="relative flex max-h-[min(50vh,22rem)] flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
          <div className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3 sm:px-5">
            {catalogBody}
          </div>
        </div>
        {modals}
      </section>
    );
  }

  return (
    <div className="hero-motion-delay flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      {error && !formOpen && !deleteTarget && (
        <p
          className="shrink-0 rounded-xl border border-red-200/80 bg-red-50 px-4 py-3 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}
      {success && (
        <p
          className="shrink-0 rounded-xl border border-emerald-200/80 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800"
          role="status"
        >
          {success}
        </p>
      )}

      <section className="surface-panel relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl">
        <div className="flex shrink-0 flex-wrap items-start justify-between gap-3 border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/35 px-5 py-5 sm:px-6">
          <div>
            <p className="section-label">Catalog</p>
            <h2 className="font-display mt-1.5 text-lg font-semibold tracking-tight text-[var(--ink)]">
              Services
            </h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {!isOwner && "Only the shop owner can change the service catalog. "}
              Add every service your shop provides.
            </p>
          </div>
          {addServiceButton}
        </div>
        <div className="table-scroll asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain px-5 py-4">
          {catalogBody}
        </div>
      </section>

      {modals}
    </div>
  );
}
