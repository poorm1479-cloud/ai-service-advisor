"use client";

import { FormEvent, useEffect, useState } from "react";
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

const DEFAULT_FORM: ServiceInput = {
  name: "",
  category: "maintenance",
  duration_minutes: 60,
  price: "0.00",
  skill: "general",
  bay: "general",
  active: true,
};

export default function ServiceCatalogPage() {
  const { session, loading: authLoading } = useAuth();
  const isOwner = session?.role === "owner";

  const [services, setServices] = useState<ShopService[]>([]);
  const [categories, setCategories] = useState<string[]>(["other"]);
  const [skills, setSkills] = useState<string[]>(["general"]);
  const [bayTypes, setBayTypes] = useState<string[]>(["general"]);
  const [form, setForm] = useState<ServiceInput>(DEFAULT_FORM);
  const [initialForm, setInitialForm] = useState<ServiceInput | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ShopService | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

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

  function openAddForm() {
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setInitialForm(null);
    setFormOpen(true);
    setSuccess(null);
    setError(null);
  }

  function startEdit(svc: ShopService) {
    const next: ServiceInput = {
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

  function resetForm() {
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setInitialForm(null);
    setFormOpen(false);
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

  const canSave =
    !!form.name.trim() && !saving && (!editingId || isFormDirty());

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!isOwner) return;
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
      duration_minutes: Number(form.duration_minutes),
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
    if (!isOwner) return;
    setDeleteTarget(svc);
    setError(null);
    setSuccess(null);
  }

  function closeDeleteConfirm() {
    if (deleting) return;
    setDeleteTarget(null);
  }

  async function onConfirmDelete() {
    if (!isOwner || !deleteTarget) return;
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
    if (!isOwner) return;
    setError(null);
    try {
      await updateShopService(svc.id, { active: !svc.active });
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update service");
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      {error && !formOpen && !deleteTarget && (
        <p className="shrink-0 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {success && (
        <p className="shrink-0 text-sm text-emerald-700" role="status">
          {success}
        </p>
      )}

      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[var(--line)] px-5 py-4">
          <h1 className="text-sm font-semibold text-[var(--ink)]">Services</h1>
          {isOwner && (
            <button
              type="button"
              onClick={openAddForm}
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
            >
              Add
            </button>
          )}
        </div>
        <div className="table-scroll asa-scroll min-h-0 flex-1 overflow-auto overscroll-contain px-5 py-4">
          {loading ? (
            <p className="text-sm text-[var(--muted)]">Loading…</p>
          ) : services.length === 0 ? (
            <p className="text-sm text-[var(--muted)]">No services yet.</p>
          ) : (
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-[var(--muted)]">
                <tr>
                  <th className="pb-2 pr-3 font-medium">Name</th>
                  <th className="pb-2 pr-3 font-medium">Category</th>
                  <th className="pb-2 pr-3 font-medium">Duration</th>
                  <th className="pb-2 pr-3 font-medium">Price</th>
                  <th className="pb-2 pr-3 font-medium">Skill</th>
                  <th className="pb-2 pr-3 font-medium">Bay</th>
                  <th className="pb-2 pr-3 font-medium">Active</th>
                  {isOwner && <th className="pb-2 font-medium">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {services.map((svc) => (
                  <tr key={svc.id} className="border-t border-[var(--line)]">
                    <td className="py-2.5 pr-3 font-medium text-[var(--ink)]">{svc.name}</td>
                    <td className="py-2.5 pr-3 text-[var(--muted)]">{svc.category}</td>
                    <td className="py-2.5 pr-3 text-[var(--muted)]">{svc.duration_minutes}m</td>
                    <td className="py-2.5 pr-3 text-[var(--muted)]">${formatPrice(svc.price)}</td>
                    <td className="py-2.5 pr-3 text-[var(--muted)]">{svc.skill}</td>
                    <td className="py-2.5 pr-3 text-[var(--muted)]">{svc.bay}</td>
                    <td className="py-2.5 pr-3">
                      {isOwner ? (
                        <button
                          type="button"
                          onClick={() => toggleActive(svc)}
                          className={svc.active ? "text-emerald-700" : "text-[var(--muted)]"}
                        >
                          {svc.active ? "Yes" : "No"}
                        </button>
                      ) : svc.active ? (
                        "Yes"
                      ) : (
                        "No"
                      )}
                    </td>
                    {isOwner && (
                      <td className="py-2.5">
                        <div className="flex gap-3">
                          <button
                            type="button"
                            onClick={() => startEdit(svc)}
                            className="text-[var(--accent)]"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => openDeleteConfirm(svc)}
                            className="text-red-600"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {isOwner && deleteTarget && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-service-title"
          onClick={closeDeleteConfirm}
        >
          <div
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="delete-service-title" className="text-sm font-semibold text-red-700">
                Delete {deleteTarget.name}?
              </h2>
              <p className="mt-2 text-sm text-[var(--muted)]">
                This service will be removed from the catalog. This cannot be undone.
              </p>
            </div>
            {error && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {error}
              </p>
            )}
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={closeDeleteConfirm}
                disabled={deleting}
                className="rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
              >
                No
              </button>
              <button
                type="button"
                onClick={() => void onConfirmDelete()}
                disabled={deleting}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {deleting ? "Deleting…" : "Yes"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isOwner && formOpen && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="service-form-title"
          onClick={resetForm}
        >
          <div
            className="w-full max-w-2xl rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-[var(--line)] px-5 py-4">
              <h2 id="service-form-title" className="text-sm font-semibold text-[var(--ink)]">
                {editingId ? "Edit service" : "Add service"}
              </h2>
            </div>
            {error && (
              <p className="mx-5 mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {error}
              </p>
            )}
            <form onSubmit={onSubmit} className="grid gap-4 px-5 py-5 sm:grid-cols-2">
              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-[var(--muted)]">Name</span>
                <input
                  required
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                />
              </label>
              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-[var(--muted)]">Category</span>
                <select
                  value={form.category}
                  onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                >
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-[var(--muted)]">Duration (min)</span>
                <input
                  type="number"
                  min={5}
                  required
                  value={form.duration_minutes}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, duration_minutes: Number(e.target.value) }))
                  }
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                />
              </label>
              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-[var(--muted)]">Price</span>
                <input
                  type="number"
                  min={0}
                  step="0.01"
                  required
                  value={form.price}
                  onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                />
              </label>
              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-[var(--muted)]">Skill</span>
                <select
                  value={form.skill}
                  onChange={(e) => setForm((f) => ({ ...f, skill: e.target.value }))}
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                >
                  {skills.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-1.5">
                <span className="text-xs font-medium text-[var(--muted)]">Bay</span>
                <select
                  value={form.bay}
                  onChange={(e) => setForm((f) => ({ ...f, bay: e.target.value }))}
                  className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm"
                >
                  {bayTypes.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--muted)] sm:col-span-2">
                <input
                  type="checkbox"
                  checked={form.active}
                  onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
                />
                Active
              </label>
              <div className="flex flex-wrap gap-2 sm:col-span-2">
                <button
                  type="submit"
                  disabled={!canSave}
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save"}
                </button>
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-md border border-[var(--line)] px-4 py-2 text-sm"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
