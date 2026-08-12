"use client";

import { FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { PasswordField } from "@/components/PasswordField";
import { CAPABILITY_LABELS, StaffCapability, getApiUrl, loadSession } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import {
  ALL_STAFF_CAPABILITIES,
  CapabilityCatalogItem,
  HIDDEN_STAFF_CAPABILITIES,
  SHOP_TEAM_ROLE_LABELS,
  STAFF_CAPABILITIES,
  ShopMember,
  ShopTeamRole,
  deriveActiveWork,
  deriveAiAssistance,
  inferShopTeamRole,
  inviteStaff,
  listCapabilityCatalog,
  listMembers,
  removeMember,
  updateMemberCapabilities,
} from "@/lib/tenant";

const HIDDEN_CAPS = new Set<StaffCapability>(HIDDEN_STAFF_CAPABILITIES);

type SeatQuota = { used: number; limit: number };

async function fetchSeatQuota(): Promise<SeatQuota | null> {
  const s = loadSession();
  if (!s) return null;
  try {
    const res = await fetch(`${getApiUrl()}/v1/billing/subscription`, {
      headers: { Authorization: `Bearer ${s.accessToken}` },
    });
    if (!res.ok) return null;
    const body = await res.json();
    const used = Number(body?.usage?.usage?.seats);
    const limit = Number(body?.usage?.limits?.seats);
    if (!Number.isFinite(used) || !Number.isFinite(limit)) return null;
    return { used, limit };
  } catch {
    return null;
  }
}

function memberInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function IconUsers({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
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

function IconUserPlus({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M19 8v6M16 11h6" />
    </svg>
  );
}

function IconUser({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function IconLock({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function IconShield({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />
    </svg>
  );
}

function IconSparkles({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M12 3v3" />
      <path d="M12 18v3" />
      <path d="M3 12h3" />
      <path d="M18 12h3" />
      <path d="m5.6 5.6 2.1 2.1" />
      <path d="m16.3 16.3 2.1 2.1" />
      <path d="m16.3 5.6-2.1 2.1" />
      <path d="m5.6 16.3 2.1-2.1" />
      <circle cx="12" cy="12" r="3.2" />
    </svg>
  );
}

function IconBriefcase({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
      <path d="M2 13h20" />
    </svg>
  );
}

function IconPhone({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.81.36 1.6.68 2.35a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.75.32 1.54.55 2.35.68A2 2 0 0 1 22 16.92Z" />
    </svg>
  );
}

function IconMail({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
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
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
      <path d="M10 11v6" />
      <path d="M14 11v6" />
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

function IconCheck({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M20 6 9 17l-5-5" />
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

export function TeamPanel() {
  const { session, loading: authLoading } = useAuth();
  const isOwner = session?.role === "owner";

  const [members, setMembers] = useState<ShopMember[]>([]);
  const [catalog, setCatalog] = useState<CapabilityCatalogItem[]>([]);
  const [seatQuota, setSeatQuota] = useState<SeatQuota | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [selectedCaps, setSelectedCaps] = useState<StaffCapability[]>([...STAFF_CAPABILITIES]);
  const [saving, setSaving] = useState(false);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState<string>("");
  const [editCaps, setEditCaps] = useState<StaffCapability[]>([]);
  const [initialEditCaps, setInitialEditCaps] = useState<StaffCapability[]>([]);
  const [savingEdit, setSavingEdit] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [pendingRemove, setPendingRemove] = useState<ShopMember | null>(null);
  /** Client-only: portal modals past overflow-hidden settings shells. */
  const [portalReady, setPortalReady] = useState(false);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  const editCapsDirty = useMemo(() => {
    if (editCaps.length !== initialEditCaps.length) return true;
    const initial = new Set(initialEditCaps);
    return editCaps.some((c) => !initial.has(c));
  }, [editCaps, initialEditCaps]);

  const catalogItems = useMemo(
    () =>
      (catalog.length
        ? catalog.map((item) => ({
            ...item,
            label: CAPABILITY_LABELS[item.id] ?? item.label,
          }))
        : ALL_STAFF_CAPABILITIES.map((id) => ({
            id,
            label: CAPABILITY_LABELS[id],
          }))
      ).filter((item) => !HIDDEN_CAPS.has(item.id)),
    [catalog],
  );

  const seatsFull = seatQuota != null && seatQuota.used >= seatQuota.limit;
  const seatPct =
    seatQuota && seatQuota.limit > 0
      ? Math.min(100, Math.round((seatQuota.used / seatQuota.limit) * 100))
      : 0;

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [memberList, caps, seats] = await Promise.all([
        listMembers(),
        listCapabilityCatalog().catch(() => [] as CapabilityCatalogItem[]),
        isOwner ? fetchSeatQuota() : Promise.resolve(null),
      ]);
      setMembers(memberList);
      setCatalog(caps);
      if (seats) {
        setSeatQuota(seats);
      } else {
        // Fall back to roster size vs known plan limit when billing is unavailable.
        setSeatQuota(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load team");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!authLoading && session) {
      void load();
    } else if (!authLoading) {
      setLoading(false);
    }
  }, [authLoading, session]);

  async function onInvite(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (password !== confirmPassword) {
      setError("Password and confirmation do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setSaving(true);
    try {
      const member = await inviteStaff({
        phone: phone.trim(),
        email: email.trim() || undefined,
        fullName: fullName.trim(),
        password,
        capabilities: selectedCaps,
      });
      setSuccess(`Invited ${member.full_name} as Staff.`);
      setFullName("");
      setPhone("");
      setEmail("");
      setPassword("");
      setConfirmPassword("");
      setSelectedCaps([...STAFF_CAPABILITIES]);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to invite member");
    } finally {
      setSaving(false);
    }
  }

  function startEdit(member: ShopMember) {
    if (member.role === "owner") return;
    const caps = [...(member.capabilities || [])];
    setEditingId(member.membership_id);
    setEditingName(member.full_name);
    setEditCaps(caps);
    setInitialEditCaps(caps);
    setSuccess(null);
    setError(null);
  }

  function closeEdit() {
    if (savingEdit) return;
    setEditingId(null);
    setEditingName("");
    setInitialEditCaps([]);
  }

  function closeInvite() {
    if (saving) return;
    setShowForm(false);
    setError(null);
  }

  async function onSaveCaps(e: FormEvent) {
    e.preventDefault();
    if (!editingId) return;
    setSavingEdit(true);
    setError(null);
    setSuccess(null);
    try {
      await updateMemberCapabilities(editingId, editCaps);
      setSuccess("Permissions updated.");
      setEditingId(null);
      setEditingName("");
      setInitialEditCaps([]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update permissions");
    } finally {
      setSavingEdit(false);
    }
  }

  function requestRemoveMember(member: ShopMember) {
    if (member.role === "owner") return;
    setError(null);
    setSuccess(null);
    setPendingRemove(member);
  }

  function closeRemoveConfirm() {
    if (removingId) return;
    setPendingRemove(null);
  }

  async function confirmRemoveMember() {
    if (!pendingRemove || pendingRemove.role === "owner") return;
    const member = pendingRemove;
    setRemovingId(member.membership_id);
    setError(null);
    setSuccess(null);
    try {
      await removeMember(member.membership_id);
      if (editingId === member.membership_id) {
        setEditingId(null);
        setEditingName("");
        setInitialEditCaps([]);
      }
      setPendingRemove(null);
      setSuccess(`Removed ${member.full_name} from the team.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove member");
    } finally {
      setRemovingId(null);
    }
  }

  function openInvite() {
    if (seatsFull) {
      setError("Seat limit reached. Upgrade your plan to add more members.");
      return;
    }
    setShowForm(true);
    setError(null);
    setSuccess(null);
  }

  if (authLoading || !session) {
    return (
      <div className="space-y-4 p-1">
        <div className="h-12 animate-pulse rounded-2xl bg-black/5" />
        <div className="h-72 animate-pulse rounded-2xl bg-black/5" />
      </div>
    );
  }

  return (
    <div className="hero-motion-delay flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      {error && !showForm && !pendingRemove && (
        <p
          className="shrink-0 rounded-xl border border-red-200/80 bg-red-50 px-4 py-3 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}
      {success && !showForm && (
        <p
          className="shrink-0 rounded-xl border border-emerald-200/80 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"
          role="status"
        >
          {success}
        </p>
      )}

      <section className="surface-panel relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl">
        <div className="shrink-0 border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/40 px-4 py-2.5 sm:px-6">
          <div className="flex min-w-0 items-center gap-2.5">
            <span
              className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]"
              aria-hidden="true"
            >
              <IconUsers className="h-3.5 w-3.5" />
            </span>
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              <h2 className="truncate text-sm font-semibold tracking-tight text-[var(--ink)]">
                Team
              </h2>
              <span className="inline-flex items-center gap-1 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-[var(--ink)] ring-1 ring-[var(--line)]">
                <IconShield className="h-2.5 w-2.5 text-[var(--accent)]" />
                Access
              </span>
              {!loading ? (
                <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-medium tabular-nums text-[var(--muted)] ring-1 ring-[var(--line)]">
                  {members.length} {members.length === 1 ? "member" : "members"}
                </span>
              ) : null}
              {!isOwner ? (
                <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-medium text-[var(--muted)] ring-1 ring-[var(--line)]">
                  View only
                </span>
              ) : null}
            </div>
          </div>
        </div>

        {isOwner && seatQuota ? (
          <div className="shrink-0 border-b border-[var(--line)] bg-white/60 px-4 py-3 sm:px-6">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                  Seat usage
                </p>
                <p className="mt-0.5 text-sm font-medium tabular-nums text-[var(--ink)]">
                  {seatQuota.used}
                  <span className="text-[var(--muted)]"> / {seatQuota.limit}</span>
                </p>
              </div>
              {seatsFull ? (
                <p className="text-xs font-medium text-amber-700">
                  Limit reached — upgrade to invite more.
                </p>
              ) : (
                <p className="text-xs text-[var(--muted)]">
                  {seatQuota.limit - seatQuota.used} seat
                  {seatQuota.limit - seatQuota.used === 1 ? "" : "s"} remaining
                </p>
              )}
            </div>
            <div
              className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-black/[0.06]"
              role="progressbar"
              aria-valuenow={seatQuota.used}
              aria-valuemin={0}
              aria-valuemax={seatQuota.limit}
              aria-label="Seat usage"
            >
              <div
                className={`h-full rounded-full transition-[width] duration-500 ease-out ${
                  seatsFull
                    ? "bg-amber-500"
                    : "bg-gradient-to-r from-[var(--accent)] to-[var(--accent)]/70"
                }`}
                style={{ width: `${seatPct}%` }}
              />
            </div>
          </div>
        ) : null}

        {loading ? (
          <div className="space-y-3 px-4 py-5 sm:px-6">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-xl border border-[var(--line)]/80 bg-white/50 p-4"
              >
                <div className="h-10 w-10 shrink-0 animate-pulse rounded-full bg-black/5" />
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="h-4 w-36 animate-pulse rounded bg-black/5" />
                  <div className="h-3 w-48 animate-pulse rounded bg-black/5" />
                  <div className="flex gap-2 pt-1">
                    <div className="h-5 w-16 animate-pulse rounded-full bg-black/5" />
                    <div className="h-5 w-20 animate-pulse rounded-full bg-black/5" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : members.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-14 text-center">
            <span className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--accent-soft)] to-white text-[var(--accent)] shadow-sm ring-1 ring-[var(--accent)]/15">
              <IconUsers className="h-6 w-6" />
            </span>
            <p className="font-display mt-4 text-base font-semibold tracking-tight text-[var(--ink)]">
              No members yet
            </p>
            <p className="mt-1.5 max-w-sm text-sm text-[var(--muted)]">
              {isOwner
                ? "Invite staff and set permissions so they can run appointments, inspections, and AI-assisted work."
                : "Shop team roles and permissions will appear here once members are invited."}
            </p>
            {isOwner ? (
              <button
                type="button"
                disabled={seatsFull}
                onClick={openInvite}
                className="btn-primary mt-5 inline-flex items-center gap-1.5 px-4 py-2 text-xs disabled:cursor-not-allowed disabled:opacity-50"
              >
                <IconPlus className="h-3.5 w-3.5" />
                Add your first member
              </button>
            ) : null}
          </div>
        ) : (
          <ul className="asa-scroll min-h-0 flex-1 divide-y divide-[var(--line)] overflow-auto overscroll-contain">
            {members.map((m) => {
              const role = inferShopTeamRole(m);
              const caps = m.capabilities || [];
              return (
                <li key={m.membership_id}>
                  <MemberCard
                    name={m.full_name}
                    phone={m.phone || undefined}
                    email={m.email || undefined}
                    role={role}
                    capabilities={caps}
                    permissionLabels={caps
                      .filter((c) => !HIDDEN_CAPS.has(c))
                      .map((c) => ({
                        id: c,
                        label: CAPABILITY_LABELS[c] ?? c,
                      }))}
                    actions={
                      isOwner && m.role !== "owner" ? (
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => startEdit(m)}
                            className="btn-ghost inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs"
                          >
                            <IconPencil className="h-3.5 w-3.5" />
                            Permissions
                          </button>
                          <button
                            type="button"
                            disabled={removingId === m.membership_id}
                            onClick={() => requestRemoveMember(m)}
                            className="inline-flex items-center gap-1.5 rounded-full border border-red-200/80 bg-white px-2.5 py-1.5 text-xs font-medium text-red-600 transition hover:bg-red-50 disabled:opacity-60"
                          >
                            <IconTrash className="h-3.5 w-3.5" />
                            {removingId === m.membership_id ? "Removing…" : "Remove"}
                          </button>
                        </div>
                      ) : undefined
                    }
                  />
                </li>
              );
            })}
          </ul>
        )}

        {isOwner ? (
          <button
            type="button"
            disabled={seatsFull}
            aria-label="Add member"
            title={
              seatsFull
                ? "Seat limit reached. Upgrade your plan to add more members."
                : "Add member"
            }
            onClick={openInvite}
            className="btn-primary absolute bottom-2.5 right-4 z-10 inline-flex h-9 w-9 items-center justify-center p-0 shadow-md disabled:cursor-not-allowed disabled:opacity-50"
          >
            <IconUserPlus className="h-4 w-4" />
          </button>
        ) : null}
      </section>

      {portalReady &&
        createPortal(
          <>
      {isOwner && showForm && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="invite-member-title"
          onClick={closeInvite}
        >
          <form
            onSubmit={onInvite}
            className="flex max-h-[min(88dvh,36rem)] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 pb-4 pt-5">
              <div
                className="pointer-events-none absolute right-0 top-0 h-32 w-32 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                aria-hidden="true"
              />
              <div className="relative flex min-w-0 items-center gap-2.5">
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]">
                  <IconUserPlus className="h-3.5 w-3.5" />
                </span>
                <h2
                  id="invite-member-title"
                  className="text-base font-semibold tracking-tight text-[var(--ink)]"
                >
                  Add member
                </h2>
              </div>
            </div>

            <div className="asa-scroll min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-5 py-3.5">
              <div className="grid grid-cols-2 items-start gap-x-4 gap-y-3">
                <Field
                  label="Full name"
                  icon={<IconUser />}
                  value={fullName}
                  onChange={setFullName}
                  required
                />
                <Field
                  label="Phone"
                  icon={<IconPhone />}
                  value={phone}
                  onChange={(v) => setPhone(formatPhoneInput(v))}
                  type="tel"
                  placeholder={PHONE_PLACEHOLDER}
                  required
                />
                <Field
                  label="Email (optional)"
                  icon={<IconMail />}
                  type="email"
                  value={email}
                  onChange={setEmail}
                />
                <div className="col-span-2 grid grid-cols-2 items-start gap-x-4 gap-y-3">
                  <PasswordField
                    label="Password"
                    icon={<IconLock />}
                    value={password}
                    onChange={setPassword}
                    required
                    minLength={8}
                    autoComplete="new-password"
                  />
                  <div className="space-y-1.5">
                    <PasswordField
                      label="Confirm password"
                      icon={<IconLock />}
                      value={confirmPassword}
                      onChange={setConfirmPassword}
                      required
                      minLength={8}
                      autoComplete="new-password"
                    />
                    {confirmPassword && password !== confirmPassword ? (
                      <p className="text-xs text-red-600">Passwords do not match.</p>
                    ) : null}
                  </div>
                </div>
              </div>

              <fieldset>
                <legend className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--ink)]">
                  <span className="text-[var(--muted)]">
                    <IconBriefcase />
                  </span>
                  Role
                </legend>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Invited members are always Staff. Access is controlled by permissions below.
                </p>
                <div className="mt-3">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--accent-soft)] px-3 py-1.5 text-xs font-semibold text-[var(--accent)] ring-1 ring-inset ring-[var(--accent)]/20">
                    <IconShield className="h-3 w-3" />
                    Staff
                  </span>
                </div>
              </fieldset>

              <CapabilityChecklist
                items={catalogItems}
                selected={selectedCaps}
                onChange={setSelectedCaps}
                desktopLayout
              />

              {error && (
                <p
                  className="rounded-xl border border-red-200/80 bg-red-50 px-3 py-2 text-sm text-red-700"
                  role="alert"
                >
                  {error}
                </p>
              )}
            </div>

            <div className="flex shrink-0 flex-nowrap justify-end gap-2 border-t border-[var(--line)] bg-white/70 px-5 py-3">
              <button
                type="button"
                onClick={closeInvite}
                disabled={saving}
                className="btn-ghost inline-flex items-center gap-1.5 px-3 py-1.5 text-sm disabled:opacity-60"
              >
                <IconX className="h-3.5 w-3.5" />
                Cancel
              </button>
              <button
                type="submit"
                disabled={
                  saving ||
                  selectedCaps.length === 0 ||
                  password.length < 8 ||
                  confirmPassword.length < 8 ||
                  password !== confirmPassword
                }
                className="btn-primary inline-flex items-center gap-1.5 px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                <IconSave className="h-3.5 w-3.5" />
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      )}

      {pendingRemove && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="remove-member-title"
          onClick={closeRemoveConfirm}
        >
          <div
            className="w-full max-w-[26rem] overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative overflow-hidden border-b border-red-100 bg-gradient-to-br from-red-50 via-white to-white px-5 pb-5 pt-6">
              <div
                className="pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-red-100/70 blur-2xl"
                aria-hidden="true"
              />
              <div className="relative flex items-center gap-4">
                <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-red-600 text-white shadow-lg shadow-red-600/25">
                  <IconTrash className="h-5 w-5" />
                </span>
                <h2
                  id="remove-member-title"
                  className="text-lg font-semibold tracking-tight text-slate-900"
                >
                  Remove team member
                </h2>
              </div>
            </div>

            <div className="space-y-4 px-5 py-5">
              <p className="text-sm leading-relaxed text-[var(--muted)]">
                Remove{" "}
                <span className="font-medium text-[var(--ink)]">{pendingRemove.full_name}</span>{" "}
                from the team? They will lose access immediately.
              </p>
              {error && (
                <p
                  className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                  role="alert"
                >
                  {error}
                </p>
              )}
              <div className="flex flex-nowrap justify-end gap-2">
                <button
                  type="button"
                  onClick={closeRemoveConfirm}
                  disabled={!!removingId}
                  className="btn-ghost px-4 py-2 text-sm disabled:opacity-60"
                >
                  No
                </button>
                <button
                  type="button"
                  onClick={() => void confirmRemoveMember()}
                  disabled={!!removingId}
                  className="inline-flex items-center justify-center rounded-full bg-red-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm shadow-red-600/20 transition hover:bg-red-700 disabled:opacity-60"
                >
                  {removingId ? "Removing…" : "Yes"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {isOwner && editingId && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-permissions-title"
          onClick={closeEdit}
        >
          <form
            onSubmit={onSaveCaps}
            className="flex max-h-[min(90dvh,38rem)] w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="relative shrink-0 overflow-hidden rounded-t-2xl border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 pb-4 pt-5">
              <div
                className="pointer-events-none absolute right-0 top-0 h-40 w-40 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                aria-hidden="true"
              />
              <div className="relative flex min-w-0 items-center gap-2.5">
                <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-[11px] font-semibold tracking-wide text-white shadow-md shadow-[var(--accent-glow)]">
                  {memberInitials(editingName || "?")}
                </span>
                <h2
                  id="edit-permissions-title"
                  className="min-w-0 truncate text-base font-semibold tracking-tight text-[var(--ink)]"
                >
                  Edit permissions
                  {editingName ? ` · ${editingName}` : ""}
                </h2>
              </div>
            </div>
            <div className="asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-3.5">
              <CapabilityChecklist
                items={catalogItems}
                selected={editCaps}
                onChange={setEditCaps}
                desktopLayout
              />
            </div>
            <div className="flex shrink-0 flex-nowrap justify-end gap-2 border-t border-[var(--line)] bg-white/70 px-5 py-3">
              <button
                type="button"
                onClick={closeEdit}
                disabled={savingEdit}
                className="btn-ghost inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs disabled:opacity-60"
              >
                <IconX className="h-3.5 w-3.5" />
                Cancel
              </button>
              <button
                type="submit"
                disabled={savingEdit || !editCapsDirty}
                className="btn-primary inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
              >
                <IconSave className="h-3.5 w-3.5" />
                {savingEdit ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        </div>
      )}
          </>,
          document.body,
        )}
    </div>
  );
}

function MemberCard({
  name,
  phone,
  email,
  role,
  capabilities,
  permissionLabels,
  actions,
}: {
  name: string;
  phone?: string;
  email?: string;
  role: ShopTeamRole;
  capabilities: StaffCapability[];
  permissionLabels: { id: string; label: string }[];
  actions?: ReactNode;
}) {
  const activeWork =
    role === "owner" && capabilities.length === 0
      ? "Shop oversight"
      : deriveActiveWork(capabilities);
  const aiAssistance =
    role === "owner" && capabilities.length === 0
      ? "On · full shop"
      : deriveAiAssistance(capabilities);
  const isOwner = role === "owner";

  return (
    <div className="group px-4 py-4 transition-colors hover:bg-[var(--accent-soft)]/25 sm:px-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <span
            className={`mt-0.5 inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-xs font-semibold tracking-wide shadow-sm ring-1 ${
              isOwner
                ? "bg-[var(--accent)] text-white shadow-[var(--accent-glow)] ring-[var(--accent)]/20"
                : "bg-gradient-to-br from-[var(--accent-soft)] to-white text-[var(--accent)] ring-[var(--accent)]/15"
            }`}
            aria-hidden="true"
          >
            {memberInitials(name)}
          </span>
          <div className="min-w-0 flex-1 space-y-2.5 text-left">
            <div>
              <div className="flex flex-col items-start gap-1.5 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
                <p className="w-full truncate text-sm font-semibold leading-5 tracking-tight text-[var(--ink)] sm:w-auto">
                  {name}
                </p>
                <span
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold leading-4 ring-1 ${
                    isOwner
                      ? "bg-[var(--accent-soft)] text-[var(--accent)] ring-[var(--accent)]/20"
                      : "bg-white/90 text-[var(--ink)] ring-[var(--line)]"
                  }`}
                >
                  <IconShield className="h-2.5 w-2.5 shrink-0" />
                  {SHOP_TEAM_ROLE_LABELS[role]}
                </span>
              </div>
              {phone || email ? (
                <div className="mt-1.5 flex flex-nowrap items-center gap-x-3 text-xs leading-4 text-[var(--muted)] sm:mt-1">
                  {phone ? (
                    <span className="inline-flex min-w-0 shrink items-center gap-1.5">
                      <IconPhone className="h-3 w-3 shrink-0 text-[var(--accent)]/80" />
                      <span className="min-w-0 truncate">{phone}</span>
                    </span>
                  ) : null}
                  {email ? (
                    <span className="inline-flex min-w-0 shrink items-center gap-1.5">
                      <IconMail className="h-3 w-3 shrink-0 text-[var(--accent)]/80" />
                      <span className="min-w-0 truncate">{email}</span>
                    </span>
                  ) : null}
                </div>
              ) : null}
            </div>

            <div className="flex flex-col gap-1.5 text-xs leading-4 text-[var(--muted)] sm:flex-row sm:flex-wrap sm:gap-x-4">
              <span className="inline-flex min-w-0 items-center gap-1.5">
                <IconBriefcase className="h-3 w-3 shrink-0 text-[var(--accent)]/80" />
                <span className="min-w-0">
                  <span className="text-[var(--muted)]">Work </span>
                  <span className="font-medium text-[var(--ink)]">{activeWork}</span>
                </span>
              </span>
              <span className="inline-flex min-w-0 items-center gap-1.5">
                <IconSparkles className="h-3 w-3 shrink-0 text-[var(--accent)]/80" />
                <span className="min-w-0">
                  <span className="text-[var(--muted)]">AI </span>
                  <span className="font-medium text-[var(--ink)]">{aiAssistance}</span>
                </span>
              </span>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {isOwner && permissionLabels.length === 0 ? (
                <span className="rounded-full bg-black/[0.04] px-2.5 py-0.5 text-[11px] font-medium leading-4 text-[var(--muted)] ring-1 ring-inset ring-black/5">
                  Full access
                </span>
              ) : permissionLabels.length > 0 ? (
                permissionLabels.map((p) => (
                  <span
                    key={p.id}
                    className="rounded-full bg-white/90 px-2.5 py-0.5 text-[11px] font-medium leading-4 text-[var(--muted)] ring-1 ring-[var(--line)] transition group-hover:bg-white"
                  >
                    {p.label}
                  </span>
                ))
              ) : (
                <span className="text-xs leading-4 text-[var(--muted)]">No permissions listed</span>
              )}
            </div>
          </div>
        </div>
        {actions ? (
          <div className="shrink-0 self-stretch pl-[3.25rem] sm:self-start sm:pl-0 sm:pt-1">
            {actions}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function CapabilityChecklist({
  items,
  selected,
  onChange,
  desktopLayout = false,
}: {
  items: CapabilityCatalogItem[];
  selected: StaffCapability[];
  onChange: (next: StaffCapability[]) => void;
  desktopLayout?: boolean;
}) {
  return (
    <fieldset>
      <legend className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--ink)]">
        <span className="text-[var(--muted)]">
          <IconShield />
        </span>
        Permissions
      </legend>
      <p className="mt-1 text-xs text-[var(--muted)]">
        Choose what this person can do across the shop floor and desk.
      </p>
      <ul
        className={`mt-3 grid gap-2 ${desktopLayout ? "grid-cols-2" : "grid-cols-1 sm:grid-cols-2"}`}
      >
        {items.map((item) => {
          const checked = selected.includes(item.id);
          return (
            <li key={item.id}>
              <label
                className={`flex cursor-pointer items-start gap-2.5 rounded-xl border px-3 py-2.5 text-sm transition ${
                  checked
                    ? "border-[var(--accent)]/35 bg-[var(--accent-soft)]/70 ring-1 ring-[var(--accent)]/15"
                    : "border-[var(--line)] bg-white/80 hover:bg-[var(--accent-soft)]/40"
                }`}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  checked={checked}
                  onChange={(e) => {
                    if (e.target.checked) {
                      onChange(selected.includes(item.id) ? selected : [...selected, item.id]);
                    } else {
                      onChange(selected.filter((c) => c !== item.id));
                    }
                  }}
                />
                <span
                  className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded border transition ${
                    checked
                      ? "border-[var(--accent)] bg-[var(--accent)] text-white"
                      : "border-[var(--line)] bg-white text-transparent"
                  }`}
                  aria-hidden="true"
                >
                  <IconCheck className="h-2.5 w-2.5" />
                </span>
                <span className="min-w-0">
                  <span className="font-medium text-[var(--ink)]">{item.label}</span>
                  <span className="mt-0.5 block truncate text-[10px] uppercase tracking-[0.08em] text-[var(--muted)]">
                    {item.id.replace(/_/g, " ")}
                  </span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

function Field({
  label,
  icon,
  value,
  onChange,
  type = "text",
  required,
  minLength,
  hint,
  placeholder,
  autoComplete,
}: {
  label: string;
  icon?: ReactNode;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  minLength?: number;
  hint?: string;
  placeholder?: string;
  autoComplete?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="inline-flex items-center gap-1.5 font-medium text-[var(--ink)]">
        {icon ? <span className="text-[var(--muted)]">{icon}</span> : null}
        {label}
      </span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        minLength={minLength}
        className="mt-1.5 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] transition focus:ring-2"
      />
      {hint && <span className="mt-1 block text-xs text-[var(--muted)]">{hint}</span>}
    </label>
  );
}
