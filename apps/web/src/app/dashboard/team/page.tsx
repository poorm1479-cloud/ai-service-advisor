"use client";

import { FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { PasswordField } from "@/components/PasswordField";
import { CAPABILITY_LABELS, StaffCapability } from "@/lib/api";
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

export default function TeamPage() {
  const { session, loading: authLoading } = useAuth();
  const isOwner = session?.role === "owner";

  const [members, setMembers] = useState<ShopMember[]>([]);
  const [catalog, setCatalog] = useState<CapabilityCatalogItem[]>([]);
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
  const [editCaps, setEditCaps] = useState<StaffCapability[]>([]);
  const [savingEdit, setSavingEdit] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

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

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [memberList, caps] = await Promise.all([
        listMembers(),
        listCapabilityCatalog().catch(() => [] as CapabilityCatalogItem[]),
      ]);
      setMembers(memberList);
      setCatalog(caps);
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
    setEditingId(member.membership_id);
    setEditCaps([...(member.capabilities || [])]);
    setSuccess(null);
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
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update permissions");
    } finally {
      setSavingEdit(false);
    }
  }

  async function onRemoveMember(member: ShopMember) {
    if (member.role === "owner") return;
    const confirmed = window.confirm(
      `Remove ${member.full_name} from the team? They will lose access immediately.`,
    );
    if (!confirmed) return;
    setRemovingId(member.membership_id);
    setError(null);
    setSuccess(null);
    try {
      await removeMember(member.membership_id);
      if (editingId === member.membership_id) setEditingId(null);
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
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="page-title">Team</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {isOwner
              ? "Invite shop members as Staff and set their permissions for day-to-day work."
              : "Shop team roles and permissions. Only the Owner can invite members or change access."}
          </p>
        </div>
        {isOwner ? (
          <button
            type="button"
            onClick={() => {
              setShowForm((v) => !v);
              setError(null);
              setSuccess(null);
            }}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
          >
            {showForm ? "Close" : "Invite member"}
          </button>
        ) : null}
      </div>

      {isOwner && showForm && (
        <form
          onSubmit={onInvite}
          className="space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4"
        >
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
            {saving ? "Inviting…" : "Invite member"}
          </button>
        </form>
      )}

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {success && (
        <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800" role="status">
          {success}
        </p>
      )}

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="border-b border-[var(--line)] px-4 py-3">
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
          <ul className="divide-y divide-[var(--line)]">
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
                            onClick={() =>
                              editingId === m.membership_id ? setEditingId(null) : startEdit(m)
                            }
                            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm text-[var(--muted)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]"
                          >
                            {editingId === m.membership_id ? "Cancel" : "Edit permissions"}
                          </button>
                          <button
                            type="button"
                            disabled={removingId === m.membership_id}
                            onClick={() => void onRemoveMember(m)}
                            className="rounded-md border border-[var(--line)] px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 disabled:opacity-60"
                          >
                            {removingId === m.membership_id ? "Removing…" : "Remove"}
                          </button>
                        </div>
                      ) : undefined
                    }
                  />
                  {isOwner && editingId === m.membership_id && (
                    <form
                      onSubmit={onSaveCaps}
                      className="space-y-3 border-t border-[var(--line)] px-4 py-4"
                    >
                      <p className="text-xs text-[var(--muted)]">
                        Adjust permissions for this Staff member. Changes apply immediately.
                      </p>
                      <CapabilityChecklist
                        items={catalogItems}
                        selected={editCaps}
                        onChange={setEditCaps}
                      />
                      <button
                        type="submit"
                        disabled={savingEdit}
                        className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                      >
                        {savingEdit ? "Saving…" : "Save permissions"}
                      </button>
                    </form>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </section>
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
