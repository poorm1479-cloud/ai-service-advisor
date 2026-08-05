"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
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
  const [editingId, setEditingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
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

  function startEdit(svc: ShopService) {
    setEditingId(svc.id);
    setForm({
      name: svc.name,
      category: svc.category,
      duration_minutes: svc.duration_minutes,
      price: formatPrice(svc.price),
      skill: svc.skill,
      bay: svc.bay,
      active: svc.active,
    });
    setSuccess(null);
    setError(null);
  }

  function resetForm() {
    setEditingId(null);
    setForm(DEFAULT_FORM);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!isOwner) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    const payload: ServiceInput = {
      ...form,
      name: form.name.trim(),
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

  async function onDelete(id: string) {
    if (!isOwner) return;
    if (!window.confirm("Delete this service?")) return;
    setError(null);
    setSuccess(null);
    try {
      await deleteShopService(id);
      if (editingId === id) resetForm();
      setSuccess("Service deleted.");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete service");
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
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Service catalog</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Services used for AI phone scheduling — name, category, duration, price, skill, bay, and
          active status.{" "}
          <Link href="/dashboard/settings" className="text-[var(--accent)] underline-offset-2 hover:underline">
            Shop settings
          </Link>
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {success && (
        <p className="text-sm text-emerald-700" role="status">
          {success}
        </p>
      )}

      {isOwner && (
        <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)]">
          <div className="border-b border-[var(--line)] px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--ink)]">
              {editingId ? "Edit service" : "Add service"}
            </h2>
          </div>
          <form onSubmit={onSubmit} className="grid gap-4 px-5 py-5 sm:grid-cols-2 lg:grid-cols-3">
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
            <label className="flex items-center gap-2 text-sm text-[var(--muted)] sm:col-span-2 lg:col-span-3">
              <input
                type="checkbox"
                checked={form.active}
                onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
              />
              Active
            </label>
            <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-3">
              <button
                type="submit"
                disabled={saving || !form.name.trim()}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {saving ? "Saving…" : editingId ? "Save changes" : "Add service"}
              </button>
              {editingId && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="rounded-md border border-[var(--line)] px-4 py-2 text-sm"
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </section>
      )}

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--ink)]">Catalog</h2>
        </div>
        <div className="overflow-x-auto px-5 py-4">
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
                            onClick={() => onDelete(svc.id)}
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
    </div>
  );
}
