"use client";

import { FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
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

export default function TeamPage() {
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
      setError("Temporary password and confirmation do not match.");
      return;
    }
    if (password.length < 8) {
      setError("Temporary password must be at least 8 characters.");
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

  if (authLoading || !session) {
    return <p className="text-sm text-[var(--muted)]">Loading…</p>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Team</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {isOwner
              ? "Invite shop members as Staff and set their permissions for day-to-day work."
              : "Shop team roles and permissions. Only the Owner can invite members or change access."}
          </p>
          {isOwner && seatQuota ? (
            <p className="mt-1 text-xs text-[var(--muted)]">
              Seats {seatQuota.used}/{seatQuota.limit}
              {seatsFull ? " — upgrade your plan to add more members." : ""}
            </p>
          ) : null}
        </div>
        {isOwner ? (
          <button
            type="button"
            disabled={seatsFull}
            title={
              seatsFull
                ? "Seat limit reached. Upgrade your plan to add more members."
                : undefined
            }
            onClick={() => {
              if (seatsFull) {
                setError("Seat limit reached. Upgrade your plan to add more members.");
                return;
              }
              setShowForm(true);
              setError(null);
              setSuccess(null);
            }}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            Add member
          </button>
        ) : null}
      </div>

      {error && !showForm && (
        <p className="shrink-0 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {success && !showForm && (
        <p className="shrink-0 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800" role="status">
          {success}
        </p>
      )}

      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="shrink-0 border-b border-[var(--line)] px-4 py-3">
          <h2 className="text-sm font-medium">Team Members</h2>
          <p className="mt-0.5 text-xs text-[var(--muted)]">
            Name, role, active work, AI assistance, and permissions for each person.
          </p>
        </div>

        {loading ? (
          <p className="px-4 py-3 text-sm text-[var(--muted)]">Loading members…</p>
        ) : members.length === 0 ? (
          <p className="px-4 py-3 text-sm text-[var(--muted)]">No members yet.</p>
        ) : (
          <ul className="asa-scroll min-h-0 flex-1 divide-y divide-[var(--line)] overflow-auto overscroll-contain">
            {members.map((m) => {
              const role = inferShopTeamRole(m);
              const caps = m.capabilities || [];
              return (
                <li key={m.membership_id}>
                  <MemberCard
                    name={m.full_name}
                    contact={[m.phone, m.email].filter(Boolean).join(" · ") || undefined}
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
                            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm text-[var(--muted)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]"
                          >
                            Edit permissions
                          </button>
                          <button
                            type="button"
                            disabled={removingId === m.membership_id}
                            onClick={() => requestRemoveMember(m)}
                            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 disabled:opacity-60"
                          >
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
      </section>

      {isOwner && showForm && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="invite-member-title"
          onClick={closeInvite}
        >
          <form
            onSubmit={onInvite}
            className="asa-scroll flex max-h-[min(90vh,40rem)] w-full max-w-lg flex-col space-y-4 overflow-y-auto overscroll-contain rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="invite-member-title" className="text-sm font-semibold">
                Add member
              </h2>
              <p className="mt-1 text-xs text-[var(--muted)]">
                Create a Staff account and set their permissions for day-to-day work.
              </p>
            </div>

            <div className="grid items-start gap-x-4 gap-y-3 sm:grid-cols-2">
              <Field label="Full name" value={fullName} onChange={setFullName} required />
              <Field
                label="Phone"
                value={phone}
                onChange={(v) => setPhone(formatPhoneInput(v))}
                type="tel"
                placeholder={PHONE_PLACEHOLDER}
                required
              />
              <Field label="Email (optional)" type="email" value={email} onChange={setEmail} />
              <div className="sm:col-span-2 grid items-start gap-x-4 gap-y-3 sm:grid-cols-2">
                <PasswordField
                  label="Temporary password"
                  value={password}
                  onChange={setPassword}
                  required
                  minLength={8}
                  autoComplete="new-password"
                  hint="At least 8 characters. Share with the member to sign in."
                />
                <div className="space-y-1.5">
                  <PasswordField
                    label="Confirm temporary password"
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
              <legend className="text-sm font-medium">Role</legend>
              <p className="mt-1 text-xs text-[var(--muted)]">
                Invited members are always Staff. Access is controlled by the permissions below.
              </p>
              <div className="mt-3">
                <span className="inline-flex rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-sm text-[var(--accent)]">
                  Staff
                </span>
              </div>
            </fieldset>

            <CapabilityChecklist
              items={catalogItems}
              selected={selectedCaps}
              onChange={setSelectedCaps}
            />

            {error && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {error}
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={
                  saving ||
                  selectedCaps.length === 0 ||
                  password.length < 8 ||
                  confirmPassword.length < 8 ||
                  password !== confirmPassword
                }
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {saving ? "Adding…" : "Add member"}
              </button>
              <button
                type="button"
                onClick={closeInvite}
                disabled={saving}
                className="rounded-md border border-[var(--line)] px-4 py-2 text-sm text-[var(--muted)] disabled:opacity-60"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {pendingRemove && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="remove-member-title"
          onClick={closeRemoveConfirm}
        >
          <div
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="remove-member-title" className="text-sm font-semibold">
                Remove team member
              </h2>
              <p className="mt-2 text-sm text-[var(--muted)]">
                Remove <span className="font-medium text-[var(--fg)]">{pendingRemove.full_name}</span> from
                the team? They will lose access immediately.
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
                onClick={closeRemoveConfirm}
                disabled={!!removingId}
                className="rounded-md border border-[var(--line)] px-4 py-2 text-sm text-[var(--muted)] disabled:opacity-60"
              >
                No
              </button>
              <button
                type="button"
                onClick={() => void confirmRemoveMember()}
                disabled={!!removingId}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {removingId ? "Removing…" : "Yes"}
              </button>
            </div>
          </div>
        </div>
      )}

      {isOwner && editingId && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="edit-permissions-title"
          onClick={closeEdit}
        >
          <form
            onSubmit={onSaveCaps}
            className="asa-scroll flex max-h-[min(90vh,40rem)] w-full max-w-lg flex-col space-y-4 overflow-y-auto overscroll-contain rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="edit-permissions-title" className="text-sm font-semibold">
                Edit permissions{editingName ? ` · ${editingName}` : ""}
              </h2>
              <p className="mt-1 text-xs text-[var(--muted)]">
                Adjust permissions for this Staff member. Changes apply immediately.
              </p>
            </div>
            <CapabilityChecklist
              items={catalogItems}
              selected={editCaps}
              onChange={setEditCaps}
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={savingEdit || !editCapsDirty}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              >
                {savingEdit ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                onClick={closeEdit}
                disabled={savingEdit}
                className="rounded-md border border-[var(--line)] px-4 py-2 text-sm text-[var(--muted)] disabled:opacity-60"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

function MemberCard({
  name,
  contact,
  role,
  capabilities,
  permissionLabels,
  actions,
}: {
  name: string;
  contact?: string;
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

  return (
    <div className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <div>
            <p className="text-sm font-medium">{name}</p>
            {contact && <p className="text-xs text-[var(--muted)]">{contact}</p>}
          </div>
          <dl className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <dt className="text-[var(--muted)]">Role</dt>
              <dd className="mt-0.5 font-medium">{SHOP_TEAM_ROLE_LABELS[role]}</dd>
            </div>
            <div>
              <dt className="text-[var(--muted)]">Active work</dt>
              <dd className="mt-0.5 font-medium">{activeWork}</dd>
            </div>
            <div className="sm:col-span-2 lg:col-span-1">
              <dt className="text-[var(--muted)]">AI assistance</dt>
              <dd className="mt-0.5 font-medium">{aiAssistance}</dd>
            </div>
          </dl>
          <div>
            <p className="text-xs text-[var(--muted)]">Permissions</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {role === "owner" && permissionLabels.length === 0 ? (
                <span className="rounded border border-[var(--line)] px-2 py-0.5 text-[11px] text-[var(--muted)]">
                  Full access
                </span>
              ) : permissionLabels.length > 0 ? (
                permissionLabels.map((p) => (
                  <span
                    key={p.id}
                    className="rounded border border-[var(--line)] px-2 py-0.5 text-[11px] text-[var(--muted)]"
                  >
                    {p.label}
                  </span>
                ))
              ) : (
                <span className="text-xs text-[var(--muted)]">No permissions listed</span>
              )}
            </div>
          </div>
        </div>
        {actions}
      </div>
    </div>
  );
}

function CapabilityChecklist({
  items,
  selected,
  onChange,
}: {
  items: CapabilityCatalogItem[];
  selected: StaffCapability[];
  onChange: (next: StaffCapability[]) => void;
}) {
  return (
    <fieldset>
      <legend className="text-sm font-medium">Permissions</legend>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {items.map((item) => {
          const checked = selected.includes(item.id);
          return (
            <li key={item.id}>
              <label className="flex cursor-pointer items-start gap-2 rounded-md border border-[var(--line)] px-3 py-2 text-sm hover:bg-[var(--accent-soft)]">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={checked}
                  onChange={(e) => {
                    if (e.target.checked) {
                      onChange(selected.includes(item.id) ? selected : [...selected, item.id]);
                    } else {
                      onChange(selected.filter((c) => c !== item.id));
                    }
                  }}
                />
                <span>
                  <span className="font-medium">{item.label}</span>
                  <span className="mt-0.5 block text-xs text-[var(--muted)]">{item.id}</span>
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
      <span className="font-medium">{label}</span>
      <input
        type={type}
        value={value}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        minLength={minLength}
        className="mt-1 w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
      />
      {hint && <span className="mt-1 block text-xs text-[var(--muted)]">{hint}</span>}
    </label>
  );
}
