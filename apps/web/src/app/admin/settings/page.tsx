"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { AdminShell, Panel } from "@/components/admin/AdminShell";
import { PasswordField } from "@/components/PasswordField";
import {
  AdminEditableSettings,
  AdminSettingsResponse,
  changeAdminPassword,
  getAdminProfile,
  getAdminSettings,
  streamAdminSettings,
  updateAdminProfile,
  updateAdminSettings,
} from "@/lib/admin";
import { useAuth } from "@/lib/auth";

const DEFAULT_EDITABLE: AdminEditableSettings = {
  dashboard_poll_seconds: 3,
  notification_retention_days: 90,
  toast_enabled: true,
  maintenance_mode: false,
};

export default function AdminSettingsPage() {
  return (
    <AdminShell>
      {({ accessToken, username }) => (
        <SettingsBody accessToken={accessToken} username={username} />
      )}
    </AdminShell>
  );
}

function SettingsBody({
  accessToken,
  username,
}: {
  accessToken: string;
  username: string;
}) {
  const { session, updateSession } = useAuth();
  const [data, setData] = useState<AdminSettingsResponse | null>(null);
  const [form, setForm] = useState<AdminEditableSettings>(DEFAULT_EDITABLE);
  const [fullName, setFullName] = useState(session?.fullName ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const formDirtyRef = useRef(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [next, profile] = await Promise.all([
        getAdminSettings(accessToken),
        getAdminProfile(accessToken),
      ]);
      setData(next);
      setForm({ ...DEFAULT_EDITABLE, ...next.editable });
      formDirtyRef.current = false;
      setFullName(profile.full_name);
      updateSession({ fullName: profile.full_name });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
      setData(null);
    } finally {
      setBusy(false);
    }
  }, [accessToken, updateSession]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setLive(false);
    const stop = streamAdminSettings(
      accessToken,
      (next) => {
        setData(next);
        setLive(true);
        if (!formDirtyRef.current) {
          setForm({ ...DEFAULT_EDITABLE, ...next.editable });
        }
      },
      () => setLive(false),
    );
    return stop;
  }, [accessToken]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const next = await updateAdminSettings(accessToken, {
        dashboard_poll_seconds: Number(form.dashboard_poll_seconds),
        notification_retention_days: Number(form.notification_retention_days),
        toast_enabled: form.toast_enabled,
        maintenance_mode: form.maintenance_mode,
      });
      setData(next);
      setForm({ ...DEFAULT_EDITABLE, ...next.editable });
      formDirtyRef.current = false;
      setSuccess("Settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  async function onSaveProfile(e: FormEvent) {
    e.preventDefault();
    setSavingProfile(true);
    setError(null);
    setProfileSuccess(null);
    try {
      const updated = await updateAdminProfile(accessToken, {
        fullName: fullName.trim(),
      });
      setFullName(updated.full_name);
      updateSession({ fullName: updated.full_name });
      setProfileSuccess("Admin name saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save admin name");
    } finally {
      setSavingProfile(false);
    }
  }

  async function onChangePassword(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setPasswordSuccess(null);
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation do not match.");
      return;
    }
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    setSavingPassword(true);
    try {
      await changeAdminPassword(accessToken, {
        currentPassword,
        newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordSuccess("Password updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to change password");
    } finally {
      setSavingPassword(false);
    }
  }

  if (error && !data) {
    return <p className="text-sm text-red-700">{error}</p>;
  }
  if (!data) {
    return <p className="text-sm text-[var(--muted)]">{busy ? "Loading…" : "No data"}</p>;
  }

  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-lg font-semibold tracking-tight">Settings</h1>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Account security and runtime platform knobs. Login username stays in environment
            allowlist.
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
            live
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-[var(--line)] bg-[var(--background)] text-[var(--muted)]"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${live ? "bg-emerald-500" : "bg-[var(--muted)]"}`}
          />
          {live ? "Live" : "Connecting"}
        </span>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {success ? <p className="text-sm text-emerald-700">{success}</p> : null}

      <Panel title="Admin account">
        <form onSubmit={onSaveProfile} className="space-y-4 px-5 py-4">
          <label className="block text-sm">
            <span className="font-medium">Login username</span>
            <span className="mt-0.5 block text-xs text-[var(--muted)]">
              Controlled by PLATFORM_ADMIN_USERNAMES. Cannot be changed here.
            </span>
            <input
              type="text"
              value={username}
              disabled
              className="mt-2 w-full max-w-md rounded-md border border-[var(--line)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--muted)]"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">Admin name</span>
            <span className="mt-0.5 block text-xs text-[var(--muted)]">
              Display name shown in the admin console.
            </span>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              disabled={savingProfile}
              minLength={1}
              maxLength={255}
              required
              className="mt-2 w-full max-w-md rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm disabled:opacity-60"
            />
          </label>
          {profileSuccess ? (
            <p className="text-sm text-emerald-700" role="status">
              {profileSuccess}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={savingProfile || !fullName.trim()}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {savingProfile ? "Saving…" : "Save name"}
          </button>
        </form>
      </Panel>

      <Panel title="Change password">
        <form onSubmit={onChangePassword} className="space-y-4 px-5 py-4">
          <p className="text-xs text-[var(--muted)]">
            Enter your current password, then choose a new one (at least 8 characters).
          </p>
          <div className="max-w-md space-y-3">
            <PasswordField
              label="Current password"
              value={currentPassword}
              onChange={setCurrentPassword}
              required
              autoComplete="current-password"
            />
            <PasswordField
              label="New password"
              value={newPassword}
              onChange={setNewPassword}
              required
              minLength={8}
              autoComplete="new-password"
            />
            <PasswordField
              label="Confirm new password"
              value={confirmPassword}
              onChange={setConfirmPassword}
              required
              minLength={8}
              autoComplete="new-password"
            />
          </div>
          {passwordSuccess ? (
            <p className="text-sm text-emerald-700" role="status">
              {passwordSuccess}
            </p>
          ) : null}
          <button
            type="submit"
            disabled={savingPassword || !currentPassword || !newPassword || !confirmPassword}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {savingPassword ? "Updating…" : "Update password"}
          </button>
        </form>
      </Panel>

      <form onSubmit={onSave} className="space-y-6">
        <Panel title="Operational">
          <div className="space-y-4 px-5 py-4">
            <label className="block text-sm">
              <span className="font-medium">Dashboard poll seconds</span>
              <span className="mt-0.5 block text-xs text-[var(--muted)]">
                SSE poll interval (3–60). Applies to all live admin streams.
              </span>
              <input
                type="number"
                min={3}
                max={60}
                value={form.dashboard_poll_seconds}
                onChange={(e) => {
                  formDirtyRef.current = true;
                  setForm((f) => ({
                    ...f,
                    dashboard_poll_seconds: Number(e.target.value),
                  }));
                }}
                className="mt-2 w-full max-w-xs rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
              />
            </label>

            <label className="block text-sm">
              <span className="font-medium">Notification retention (days)</span>
              <span className="mt-0.5 block text-xs text-[var(--muted)]">
                How long durable admin notifications are kept (1–365).
              </span>
              <input
                type="number"
                min={1}
                max={365}
                value={form.notification_retention_days}
                onChange={(e) => {
                  formDirtyRef.current = true;
                  setForm((f) => ({
                    ...f,
                    notification_retention_days: Number(e.target.value),
                  }));
                }}
                className="mt-2 w-full max-w-xs rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm"
              />
            </label>

            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={form.toast_enabled}
                onChange={(e) => {
                  formDirtyRef.current = true;
                  setForm((f) => ({ ...f, toast_enabled: e.target.checked }));
                }}
                className="mt-1"
              />
              <span>
                <span className="font-medium">Toast notifications</span>
                <span className="mt-0.5 block text-xs text-[var(--muted)]">
                  Show live toast popups for new admin events.
                </span>
              </span>
            </label>

            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={form.maintenance_mode}
                onChange={(e) => {
                  formDirtyRef.current = true;
                  setForm((f) => ({ ...f, maintenance_mode: e.target.checked }));
                }}
                className="mt-1"
              />
              <span>
                <span className="font-medium">Maintenance mode</span>
                <span className="mt-0.5 block text-xs text-[var(--muted)]">
                  Show a maintenance banner across the admin console.
                </span>
              </span>
            </label>

            <div className="pt-2">
              <button
                type="submit"
                disabled={saving}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save settings"}
              </button>
              {data.updated_at ? (
                <p className="mt-2 text-xs text-[var(--muted)]">
                  Last updated {new Date(data.updated_at).toLocaleString()}
                </p>
              ) : null}
            </div>
          </div>
        </Panel>
      </form>
    </>
  );
}
