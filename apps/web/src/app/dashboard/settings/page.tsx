"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { PasswordField } from "@/components/PasswordField";
import { fetchMe, ROLE_LABELS } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  BusinessHours,
  getSetupState,
  updateShopExtendedSettings,
} from "@/lib/shopSetup";
import {
  changeMyPassword,
  getNotificationPrefs,
  NotificationPrefs,
  updateMyProfile,
  updateNotificationPrefs,
} from "@/lib/tenant";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";

const DEFAULT_NOTIFICATIONS: NotificationPrefs = {
  email_appointments: true,
  email_alerts: true,
  sms_alerts: true,
  in_app: true,
};

const WEEKDAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

/** Normalize API/browser time values to HH:MM for <input type="time">. */
function normalizeTimeInput(value: string): string {
  const raw = (value || "").trim();
  const match = /^(\d{1,2}):(\d{2})/.exec(raw);
  if (!match) return raw.slice(0, 5);
  return `${match[1].padStart(2, "0")}:${match[2]}`;
}

function normalizeHours(rows: BusinessHours[]): BusinessHours[] {
  return rows.map((h) => ({
    weekday: Number(h.weekday),
    open_time: normalizeTimeInput(h.open_time),
    close_time: normalizeTimeInput(h.close_time),
    closed: Boolean(h.closed),
  }));
}

export default function SettingsPage() {
  const { session, loading: authLoading, updateSession } = useAuth();
  const isOwner = session?.role === "owner";

  const [shopName, setShopName] = useState("");
  const [shopSlug, setShopSlug] = useState("");
  const [hours, setHours] = useState<BusinessHours[]>([]);
  const [fullName, setFullName] = useState("");
  const [profilePhone, setProfilePhone] = useState("");
  const [profileEmail, setProfileEmail] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [notifications, setNotifications] = useState<NotificationPrefs>(DEFAULT_NOTIFICATIONS);

  const [loading, setLoading] = useState(true);
  const [savingShop, setSavingShop] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [savingNotifications, setSavingNotifications] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shopSuccess, setShopSuccess] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [notificationsSuccess, setNotificationsSuccess] = useState<string | null>(null);

  // Load shop/hours once per shop — do not depend on the whole session object.
  // Token refresh / updateSession would otherwise re-fetch and wipe in-progress edits.
  const shopId = session?.shopId || session?.shopSlug || null;

  useEffect(() => {
    if (authLoading || !session) return;

    setFullName(session.fullName);
    setProfilePhone(formatPhoneInput(session.phone || ""));
    setProfileEmail(session.email || "");
  }, [authLoading, session?.fullName, session?.phone, session?.email]);

  useEffect(() => {
    if (authLoading || !shopId) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getSetupState(), getNotificationPrefs()])
      .then(async ([setup, prefs]) => {
        if (cancelled) return;
        setShopName(setup.profile.name);
        setShopSlug(setup.profile.slug);
        setHours(normalizeHours(setup.business_hours));
        setNotifications(prefs);
        // Setup may have backfilled User.email from shop contact after phone signup.
        const current = session;
        if (current && (!current.email || !current.phone)) {
          try {
            const me = await fetchMe(current.accessToken);
            if (cancelled) return;
            const phone = me.phone ? String(me.phone) : null;
            const email = me.email ? String(me.email) : null;
            if (email !== current.email || phone !== current.phone) {
              updateSession({ email, phone, fullName: me.full_name });
              setFullName(me.full_name);
              setProfilePhone(formatPhoneInput(phone || ""));
              setProfileEmail(email || "");
            }
          } catch {
            // Keep session values if /me is unavailable.
          }
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load settings");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // Reload only when the shop changes — not on token refresh / profile patches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, shopId]);

  function updateHour(weekday: number, patch: Partial<BusinessHours>) {
    setHours((prev) =>
      prev.map((h) => (Number(h.weekday) === Number(weekday) ? { ...h, ...patch } : h)),
    );
  }

  async function onSaveShop(e: FormEvent) {
    e.preventDefault();
    if (!isOwner) return;
    if (hours.length !== 7) {
      setError("Business hours failed to load. Refresh the page and try again.");
      return;
    }
    setSavingShop(true);
    setError(null);
    setShopSuccess(null);
    try {
      // Explicit fields only — never omit `closed` (JSON drops undefined; API used to default false).
      const payloadHours = normalizeHours(hours);
      const updated = await updateShopExtendedSettings({
        profile: {
          name: shopName.trim(),
        },
        business_hours: payloadHours,
      });
      setShopName(updated.profile.name);
      setHours(normalizeHours(updated.business_hours));
      if (updated.profile.name !== session?.shopName) {
        updateSession({ shopName: updated.profile.name });
      }
      setShopSuccess("Shop settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save shop settings");
    } finally {
      setSavingShop(false);
    }
  }

  async function onSaveProfile(e: FormEvent) {
    e.preventDefault();
    setSavingProfile(true);
    setError(null);
    setProfileSuccess(null);
    try {
      const updated = await updateMyProfile({
        fullName: fullName.trim(),
        phone: profilePhone.trim() || null,
        email: profileEmail.trim() || null,
      });
      setFullName(updated.full_name);
      setProfilePhone(formatPhoneInput(updated.phone || ""));
      setProfileEmail(updated.email || "");
      updateSession({
        fullName: updated.full_name,
        phone: updated.phone,
        email: updated.email,
      });
      setProfileSuccess("Profile saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save profile");
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
      await changeMyPassword({
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

  async function onSaveNotifications(e: FormEvent) {
    e.preventDefault();
    setSavingNotifications(true);
    setError(null);
    setNotificationsSuccess(null);
    try {
      const updated = await updateNotificationPrefs(notifications);
      setNotifications(updated);
      setNotificationsSuccess("Notification settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save notification settings");
    } finally {
      setSavingNotifications(false);
    }
  }

  function toggleNotification(key: keyof NotificationPrefs) {
    setNotifications((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  if (authLoading || !session) {
    return <p className="text-sm text-[var(--muted)]">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="page-title">Settings</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Update shop details, security, and notification preferences.
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--ink)]">Shop</h2>
          <p className="mt-0.5 text-xs text-[var(--muted)]">
            {isOwner
              ? "Shop name and business hours for AI phone scheduling."
              : "Only the shop owner can change these settings."}{" "}
            <Link
              href="/dashboard/services"
              className="text-[var(--accent)] underline-offset-2 hover:underline"
            >
              Manage services
            </Link>
          </p>
        </div>
        <form onSubmit={onSaveShop} className="space-y-4 px-5 py-5">
          {loading ? (
            <p className="text-sm text-[var(--muted)]">Loading shop settings…</p>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block space-y-1.5 sm:col-span-2">
                  <span className="text-xs font-medium text-[var(--muted)]">Shop name</span>
                  <input
                    type="text"
                    value={shopName}
                    onChange={(e) => setShopName(e.target.value)}
                    disabled={!isOwner || savingShop}
                    minLength={2}
                    maxLength={255}
                    required
                    className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm disabled:cursor-not-allowed disabled:opacity-60"
                  />
                </label>
                <label className="block space-y-1.5 sm:col-span-2">
                  <span className="text-xs font-medium text-[var(--muted)]">Shop slug</span>
                  <input
                    type="text"
                    value={shopSlug}
                    disabled
                    className="w-full rounded-xl border border-[var(--line)] bg-[var(--background)] px-3 py-2.5 text-sm text-[var(--muted)]"
                  />
                  <span className="block text-xs text-[var(--muted)]">
                    Used at login. Cannot be changed after registration.
                  </span>
                </label>
              </div>

              <div className="space-y-3 border-t border-[var(--line)] pt-4">
                <h3 className="text-sm font-semibold text-[var(--ink)]">Business hours</h3>
                {hours.map((h) => (
                  <div
                    key={h.weekday}
                    className="grid items-center gap-3 sm:grid-cols-[8rem_auto_1fr_1fr]"
                  >
                    <span className="text-sm font-medium text-[var(--ink)]">
                      {WEEKDAY_NAMES[h.weekday]}
                    </span>
                    <label className="flex items-center gap-2 text-sm text-[var(--muted)]">
                      <input
                        type="checkbox"
                        checked={Boolean(h.closed)}
                        disabled={!isOwner || savingShop}
                        onChange={(e) => {
                          const nextClosed = e.target.checked;
                          updateHour(h.weekday, { closed: nextClosed });
                        }}
                      />
                      Closed
                    </label>
                    <input
                      type="time"
                      value={h.open_time}
                      disabled={!isOwner || savingShop || h.closed}
                      onChange={(e) => updateHour(h.weekday, { open_time: e.target.value })}
                      className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm disabled:opacity-50"
                    />
                    <input
                      type="time"
                      value={h.close_time}
                      disabled={!isOwner || savingShop || h.closed}
                      onChange={(e) => updateHour(h.weekday, { close_time: e.target.value })}
                      className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm disabled:opacity-50"
                    />
                  </div>
                ))}
              </div>

              {shopSuccess && (
                <p className="text-sm text-emerald-700" role="status">
                  {shopSuccess}
                </p>
              )}
              {isOwner && (
                <button
                  type="submit"
                  disabled={savingShop || shopName.trim().length < 2}
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {savingShop ? "Saving…" : "Save shop"}
                </button>
              )}
            </>
          )}
        </form>
      </section>

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--ink)]">Your profile</h2>
          <p className="mt-0.5 text-xs text-[var(--muted)]">
            Update your name, phone, and email. Contact changes notify platform admins.
          </p>
        </div>
        <form onSubmit={onSaveProfile} className="space-y-4 px-5 py-5">
          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-[var(--muted)]">Full name</span>
            <input
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              disabled={savingProfile}
              minLength={1}
              maxLength={255}
              required
              className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm disabled:opacity-60"
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-[var(--muted)]">Phone</span>
              <input
                type="tel"
                value={profilePhone}
                onChange={(e) => setProfilePhone(formatPhoneInput(e.target.value))}
                disabled={savingProfile}
                placeholder={PHONE_PLACEHOLDER}
                maxLength={16}
                className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm disabled:opacity-60"
              />
            </label>
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-[var(--muted)]">Email</span>
              <input
                type="email"
                value={profileEmail}
                onChange={(e) => setProfileEmail(e.target.value)}
                disabled={savingProfile}
                placeholder="you@example.com"
                maxLength={320}
                className="w-full rounded-xl border border-[var(--line)] bg-white/90 px-3 py-2.5 text-sm disabled:opacity-60"
              />
            </label>
          </div>
          <label className="block space-y-1.5">
            <span className="text-xs font-medium text-[var(--muted)]">Role</span>
            <input
              type="text"
              value={ROLE_LABELS[session.role]}
              disabled
              className="w-full rounded-xl border border-[var(--line)] bg-[var(--background)] px-3 py-2.5 text-sm text-[var(--muted)]"
            />
          </label>
          {profileSuccess && (
            <p className="text-sm text-emerald-700" role="status">
              {profileSuccess}
            </p>
          )}
          <button
            type="submit"
            disabled={savingProfile || !fullName.trim()}
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {savingProfile ? "Saving…" : "Save profile"}
          </button>
        </form>
      </section>

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--ink)]">Change password</h2>
          <p className="mt-0.5 text-xs text-[var(--muted)]">
            Enter your current password, then choose a new one (at least 8 characters).
          </p>
        </div>
        <form onSubmit={onChangePassword} className="space-y-4 px-5 py-5">
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
          {passwordSuccess && (
            <p className="text-sm text-emerald-700" role="status">
              {passwordSuccess}
            </p>
          )}
          <button
            type="submit"
            disabled={
              savingPassword ||
              !currentPassword ||
              newPassword.length < 8 ||
              confirmPassword.length < 8
            }
            className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {savingPassword ? "Updating…" : "Update password"}
          </button>
        </form>
      </section>

      <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)]">
        <div className="border-b border-[var(--line)] px-5 py-4">
          <h2 className="text-sm font-semibold text-[var(--ink)]">Notifications</h2>
          <p className="mt-0.5 text-xs text-[var(--muted)]">
            Choose which alerts you want to receive for this account.
          </p>
        </div>
        <form onSubmit={onSaveNotifications} className="space-y-4 px-5 py-5">
          {loading ? (
            <p className="text-sm text-[var(--muted)]">Loading notification settings…</p>
          ) : (
            <>
              {(
                [
                  {
                    key: "email_appointments" as const,
                    label: "Appointment emails",
                    hint: "Confirmations and schedule changes by email.",
                  },
                  {
                    key: "email_alerts" as const,
                    label: "Email alerts",
                    hint: "Important shop alerts and escalations by email.",
                  },
                  {
                    key: "sms_alerts" as const,
                    label: "SMS alerts",
                    hint: "Urgent alerts sent to your phone number.",
                  },
                  {
                    key: "in_app" as const,
                    label: "In-app notifications",
                    hint: "Show alerts inside the dashboard.",
                  },
                ] as const
              ).map((item) => (
                <label
                  key={item.key}
                  className="flex cursor-pointer items-start justify-between gap-4"
                >
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-[var(--ink)]">
                      {item.label}
                    </span>
                    <span className="mt-0.5 block text-xs text-[var(--muted)]">{item.hint}</span>
                  </span>
                  <input
                    type="checkbox"
                    checked={notifications[item.key]}
                    onChange={() => toggleNotification(item.key)}
                    disabled={savingNotifications}
                    className="mt-1 h-4 w-4 rounded border-[var(--line)]"
                  />
                </label>
              ))}
              {notificationsSuccess && (
                <p className="text-sm text-emerald-700" role="status">
                  {notificationsSuccess}
                </p>
              )}
              <button
                type="submit"
                disabled={savingNotifications}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {savingNotifications ? "Saving…" : "Save notifications"}
              </button>
            </>
          )}
        </form>
      </section>
    </div>
  );
}
