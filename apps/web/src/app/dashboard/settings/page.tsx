"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useCallback, useEffect, useState } from "react";
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

const TABS = [
  { id: "shop", label: "Shop" },
  { id: "profile", label: "Profile" },
  { id: "notifications", label: "Notifications" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function parseTab(value: string | null): TabId {
  // Legacy ?tab=password redirects into the merged Profile tab.
  if (value === "profile" || value === "password") return "profile";
  if (value === "shop" || value === "notifications") return value;
  return "shop";
}

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

function hoursEqual(a: BusinessHours[], b: BusinessHours[]): boolean {
  if (a.length !== b.length) return false;
  return a.every((row, i) => {
    const other = b[i];
    return (
      Number(row.weekday) === Number(other.weekday) &&
      row.open_time === other.open_time &&
      row.close_time === other.close_time &&
      Boolean(row.closed) === Boolean(other.closed)
    );
  });
}

function SettingsContent() {
  const { session, loading: authLoading, updateSession } = useAuth();
  const isOwner = session?.role === "owner";
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<TabId>(() => parseTab(searchParams.get("tab")));

  const [shopName, setShopName] = useState("");
  const [hours, setHours] = useState<BusinessHours[]>([]);
  /** Last saved shop fields — used to enable Save only when dirty. */
  const [savedShopName, setSavedShopName] = useState("");
  const [savedHours, setSavedHours] = useState<BusinessHours[]>([]);
  const [fullName, setFullName] = useState("");
  const [profilePhone, setProfilePhone] = useState("");
  const [profileEmail, setProfileEmail] = useState("");
  /** Last saved profile fields — used to enable Save only when dirty. */
  const [savedFullName, setSavedFullName] = useState("");
  const [savedProfilePhone, setSavedProfilePhone] = useState("");
  const [savedProfileEmail, setSavedProfileEmail] = useState("");

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [notifications, setNotifications] = useState<NotificationPrefs>(DEFAULT_NOTIFICATIONS);
  /** Last saved notification prefs — used to enable Save only when dirty. */
  const [savedNotifications, setSavedNotifications] =
    useState<NotificationPrefs>(DEFAULT_NOTIFICATIONS);

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

  useEffect(() => {
    setTab(parseTab(searchParams.get("tab")));
  }, [searchParams]);

  const selectTab = useCallback(
    (next: TabId) => {
      setTab(next);
      setError(null);
      const params = new URLSearchParams(searchParams.toString());
      params.set("tab", next);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  // Load shop/hours once per shop — do not depend on the whole session object.
  // Token refresh / updateSession would otherwise re-fetch and wipe in-progress edits.
  const shopId = session?.shopId || session?.shopSlug || null;

  useEffect(() => {
    if (authLoading || !session) return;

    const name = session.fullName;
    const phone = formatPhoneInput(session.phone || "");
    const email = session.email || "";
    setFullName(name);
    setProfilePhone(phone);
    setProfileEmail(email);
    setSavedFullName(name);
    setSavedProfilePhone(phone);
    setSavedProfileEmail(email);
  }, [authLoading, session?.fullName, session?.phone, session?.email]);

  useEffect(() => {
    if (authLoading || !shopId) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getSetupState(), getNotificationPrefs()])
      .then(async ([setup, prefs]) => {
        if (cancelled) return;
        const loadedHours = normalizeHours(setup.business_hours);
        setShopName(setup.profile.name);
        setHours(loadedHours);
        setSavedShopName(setup.profile.name);
        setSavedHours(loadedHours);
        setNotifications(prefs);
        setSavedNotifications(prefs);
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
      const nextHours = normalizeHours(updated.business_hours);
      setShopName(updated.profile.name);
      setHours(nextHours);
      setSavedShopName(updated.profile.name);
      setSavedHours(nextHours);
      if (
        updated.profile.name !== session?.shopName ||
        updated.profile.slug !== session?.shopSlug
      ) {
        updateSession({
          shopName: updated.profile.name,
          shopSlug: updated.profile.slug,
        });
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
      const nextName = updated.full_name;
      const nextPhone = formatPhoneInput(updated.phone || "");
      const nextEmail = updated.email || "";
      setFullName(nextName);
      setProfilePhone(nextPhone);
      setProfileEmail(nextEmail);
      setSavedFullName(nextName);
      setSavedProfilePhone(nextPhone);
      setSavedProfileEmail(nextEmail);
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
      setSavedNotifications(updated);
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

  const shopDirty =
    shopName.trim() !== savedShopName.trim() || !hoursEqual(normalizeHours(hours), savedHours);
  const profileDirty =
    fullName.trim() !== savedFullName.trim() ||
    profilePhone.trim() !== savedProfilePhone.trim() ||
    profileEmail.trim() !== savedProfileEmail.trim();
  const notificationsDirty =
    notifications.email_appointments !== savedNotifications.email_appointments ||
    notifications.email_alerts !== savedNotifications.email_alerts ||
    notifications.sms_alerts !== savedNotifications.sms_alerts ||
    notifications.in_app !== savedNotifications.in_app;

  if (authLoading || !session) {
    return <p className="text-sm text-[var(--muted)]">Loading…</p>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <h1 className="page-title">Settings</h1>
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Settings categories">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => selectTab(t.id)}
              className={`rounded-md border px-3 py-2 text-sm ${
                tab === t.id
                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                  : "border-[var(--line)] text-[var(--muted)]"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="shrink-0 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      {tab === "shop" && (
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
          <div className="shrink-0 border-b border-[var(--line)] px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--ink)]">Shop</h2>
            <p className="mt-0.5 text-xs text-[var(--muted)]">
              {!isOwner && "Only the shop owner can change these settings. "}
              <Link
                href="/dashboard/services"
                className="text-[var(--accent)] underline-offset-2 hover:underline"
              >
                Manage services
              </Link>
            </p>
          </div>
          <form
            onSubmit={onSaveShop}
            className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-5"
          >
            {loading ? (
              <p className="text-sm text-[var(--muted)]">Loading shop settings…</p>
            ) : (
              <>
                <label className="block space-y-1.5">
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
                    disabled={
                      savingShop ||
                      !shopDirty ||
                      shopName.trim().length < 2
                    }
                    className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  >
                    {savingShop ? "Saving…" : "Save"}
                  </button>
                )}
              </>
            )}
          </form>
        </section>
      )}

      {tab === "profile" && (
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
          <div className="shrink-0 border-b border-[var(--line)] px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--ink)]">Your profile</h2>
            <p className="mt-0.5 text-xs text-[var(--muted)]">
              Contact details and password for this account.
            </p>
          </div>
          <div className="asa-scroll min-h-0 flex-1 space-y-8 overflow-y-auto overscroll-contain px-5 py-5">
            <form onSubmit={onSaveProfile} className="space-y-4">
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
                disabled={savingProfile || !fullName.trim() || !profileDirty}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {savingProfile ? "Saving…" : "Save"}
              </button>
            </form>

            <form
              onSubmit={onChangePassword}
              className="space-y-4 border-t border-[var(--line)] pt-6"
            >
              <div>
                <h3 className="text-sm font-semibold text-[var(--ink)]">Change password</h3>
                <p className="mt-0.5 text-xs text-[var(--muted)]">
                  Enter your current password, then choose a new one (at least 8 characters).
                </p>
              </div>
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
                {savingPassword ? "Saving…" : "Save"}
              </button>
            </form>
          </div>
        </section>
      )}

      {tab === "notifications" && (
        <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)]">
          <div className="shrink-0 border-b border-[var(--line)] px-5 py-4">
            <h2 className="text-sm font-semibold text-[var(--ink)]">Notifications</h2>
            <p className="mt-0.5 text-xs text-[var(--muted)]">
              Choose which alerts you want to receive for this account.
            </p>
          </div>
          <form
            onSubmit={onSaveNotifications}
            className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-5"
          >
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
                  disabled={!notificationsDirty || savingNotifications}
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                >
                  {savingNotifications ? "Saving…" : "Save"}
                </button>
              </>
            )}
          </form>
        </section>
      )}
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-[var(--muted)]">Loading…</p>}>
      <SettingsContent />
    </Suspense>
  );
}
