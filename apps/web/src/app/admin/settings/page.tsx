"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { AdminShell, LiveBadge, Panel } from "@/components/admin/AdminShell";
import { PasswordField } from "@/components/PasswordField";
import {
  AdminEditableSettings,
  AdminSettingsResponse,
  changeAdminPassword,
  getAdminSettings,
  streamAdminSettings,
  updateAdminSettings,
} from "@/lib/admin";

const DEFAULT_EDITABLE: AdminEditableSettings = {
  dashboard_poll_seconds: 3,
  notification_retention_days: 90,
  toast_enabled: true,
  maintenance_mode: false,
  twilio_auto_provision_numbers: true,
  openai_enabled: true,
};

const POLL_MS = 3000;

export default function AdminSettingsPage() {
  return (
    <AdminShell>
      {({ accessToken }) => <SettingsBody accessToken={accessToken} />}
    </AdminShell>
  );
}

function SettingsBody({ accessToken }: { accessToken: string }) {
  const [data, setData] = useState<AdminSettingsResponse | null>(null);
  const [form, setForm] = useState<AdminEditableSettings>(DEFAULT_EDITABLE);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const formDirtyRef = useRef(false);

  const applySettings = useCallback((next: AdminSettingsResponse) => {
    setData(next);
    setLive(true);
    setError(null);
    if (!formDirtyRef.current) {
      setForm({ ...DEFAULT_EDITABLE, ...next.editable });
    }
  }, []);

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) {
        setBusy(true);
        setError(null);
      }
      try {
        applySettings(await getAdminSettings(accessToken));
        if (!quiet) formDirtyRef.current = false;
      } catch (err) {
        if (!quiet) {
          setLive(false);
          setError(err instanceof Error ? err.message : "Failed to load settings");
          setData(null);
        }
      } finally {
        if (!quiet) setBusy(false);
      }
    },
    [accessToken, applySettings],
  );

  // REST polling is the reliable live path while this page stays mounted.
  useEffect(() => {
    void load(false);
    const id = window.setInterval(() => void load(true), POLL_MS);
    const onVis = () => {
      if (document.visibilityState === "visible") void load(true);
    };
    const onRefresh = () => void load(true);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", onRefresh);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", onRefresh);
    };
  }, [load]);

  // SSE is best-effort; polls keep settings in sync if the stream stalls.
  useEffect(() => {
    const stop = streamAdminSettings(
      accessToken,
      (next) => applySettings(next),
      () => {
        /* polling keeps data fresh */
      },
    );
    return stop;
  }, [accessToken, applySettings]);

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
      applySettings(next);
      formDirtyRef.current = false;
      setSuccess("Settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h1 className="page-title">Setting</h1>
        <LiveBadge live={live} />
      </div>

      {error ? (
        <p className="rounded-xl border border-red-200/80 bg-red-50/90 px-4 py-3 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {success ? (
        <p className="rounded-xl border border-emerald-200/80 bg-emerald-50/90 px-4 py-3 text-sm text-emerald-800">
          {success}
        </p>
      ) : null}

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

            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={form.twilio_auto_provision_numbers}
                onChange={(e) => {
                  formDirtyRef.current = true;
                  setForm((f) => ({
                    ...f,
                    twilio_auto_provision_numbers: e.target.checked,
                  }));
                }}
                className="mt-1"
              />
              <span>
                <span className="font-medium">Auto-create Twilio number on account creation</span>
                <span className="mt-0.5 block text-xs text-[var(--muted)]">
                  When enabled, new shop signups get an SMS/Voice number automatically.
                  Admin can still assign numbers manually on the Twilio Numbers page.
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
