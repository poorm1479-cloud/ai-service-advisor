"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  FormEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { PasswordField } from "@/components/PasswordField";
import {
  fetchMe,
  loadRememberedLoginPassword,
  ROLE_LABELS,
  saveRememberedLoginPassword,
  saveRememberedRegisterPassword,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  BusinessHours,
  getSetupState,
  updateShopExtendedSettings,
} from "@/lib/shopSetup";
import {
  changeMyPassword,
  getShopSettings,
  updateMyProfile,
} from "@/lib/tenant";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { ServicesPanel } from "@/components/services/ServicesPanel";
import { TeamPanel } from "@/components/team/TeamPanel";

type TabId = "account" | "shop" | "team";

function IconSetting({ className = "h-5 w-5" }: { className?: string }) {
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
      <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function parseTab(value: string | null): TabId {
  // Legacy ?tab=profile / ?tab=password redirect into Account.
  if (value === "account" || value === "profile" || value === "password") {
    return "account";
  }
  // Legacy ?tab=services now lives under Shop.
  if (value === "shop" || value === "services") {
    return "shop";
  }
  if (value === "team") {
    return "team";
  }
  return "account";
}

const WEEKDAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

function profileInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
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

function IconSave({ className = "h-4 w-4" }: { className?: string }) {
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

function IconEdit({ className = "h-3.5 w-3.5" }: { className?: string }) {
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

function IconBuilding({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M3 21h18" />
      <path d="M5 21V7l7-4 7 4v14" />
      <path d="M9 21v-6h6v6" />
      <path d="M9 9h.01" />
      <path d="M15 9h.01" />
      <path d="M9 13h.01" />
      <path d="M15 13h.01" />
    </svg>
  );
}

const TABS = [
  { id: "account", label: "Account", Icon: IconUser },
  { id: "shop", label: "Shop", Icon: IconBuilding },
  { id: "team", label: "Team", Icon: IconUsers },
] as const;

/** Minimum horizontal drag distance (px) to change tabs. */
const TAB_SWIPE_THRESHOLD_PX = 56;

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
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </svg>
  );
}

function IconCopy({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
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

function ProfileField({
  label,
  icon,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
  disabled,
  maxLength,
  minLength,
}: {
  label: string;
  icon?: ReactNode;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  disabled?: boolean;
  maxLength?: number;
  minLength?: number;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="inline-flex items-center gap-1.5 text-sm font-medium">
        {icon ? <span className="text-[var(--muted)]">{icon}</span> : null}
        {label}
        {required ? <span className="text-red-600"> *</span> : null}
      </span>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        disabled={disabled}
        maxLength={maxLength}
        minLength={minLength}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2 disabled:cursor-not-allowed disabled:opacity-60"
      />
    </label>
  );
}

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

/** Display HH:MM as 12-hour label, e.g. 09:00 → 9:00 AM. */
function formatHourLabel(value: string): string {
  const match = /^(\d{1,2}):(\d{2})/.exec((value || "").trim());
  if (!match) return value || "—";
  let hour = Number(match[1]);
  const minute = match[2];
  const suffix = hour >= 12 ? "PM" : "AM";
  hour = hour % 12;
  if (hour === 0) hour = 12;
  return `${hour}:${minute} ${suffix}`;
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
  /** Assigned Twilio voice number — read-only. */
  const [twilioVoicePhone, setTwilioVoicePhone] = useState<string | null>(null);
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

  const [loading, setLoading] = useState(true);
  const [savingShop, setSavingShop] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  /** Profile fields are read-only until the user clicks Change. */
  const [editingProfile, setEditingProfile] = useState(false);
  /** Shop fields are read-only until the owner clicks Change. */
  const [editingShop, setEditingShop] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shopSuccess, setShopSuccess] = useState<string | null>(null);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);

  useEffect(() => {
    setTab(parseTab(searchParams.get("tab")));
  }, [searchParams]);

  const selectTab = useCallback(
    (next: TabId) => {
      setTab(next);
      setError(null);
      setEditingProfile(false);
      setEditingShop(false);
      const params = new URLSearchParams(searchParams.toString());
      params.set("tab", next);
      router.replace(`${pathname}?${params.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  /** Horizontal click-drag / swipe on the page body switches adjacent tabs. */
  const swipeRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
  } | null>(null);

  const onSwipePointerDown = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const el = e.target as HTMLElement | null;
    if (
      el?.closest(
        "input, textarea, select, button, a, label, [role='tab'], [role='dialog'], [aria-modal='true'], [contenteditable='true']",
      )
    ) {
      return;
    }
    // Avoid highlighting body copy while click-dragging to change tabs.
    window.getSelection()?.removeAllRanges();
    swipeRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  }, []);

  const onSwipePointerUp = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      const start = swipeRef.current;
      swipeRef.current = null;
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
      if (!start || start.pointerId !== e.pointerId) return;

      const dx = e.clientX - start.startX;
      const dy = e.clientY - start.startY;
      if (Math.abs(dx) < TAB_SWIPE_THRESHOLD_PX) return;
      // Prefer vertical scroll when the gesture is mostly vertical.
      if (Math.abs(dx) < Math.abs(dy) * 1.15) return;

      const idx = TABS.findIndex((t) => t.id === tab);
      if (idx < 0) return;
      if (dx < 0 && idx < TABS.length - 1) {
        selectTab(TABS[idx + 1].id);
      } else if (dx > 0 && idx > 0) {
        selectTab(TABS[idx - 1].id);
      }
    },
    [selectTab, tab],
  );

  const onSwipePointerCancel = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    swipeRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
  }, []);

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
    Promise.all([getSetupState(), getShopSettings()])
      .then(async ([setup, shop]) => {
        if (cancelled) return;
        const loadedHours = normalizeHours(setup.business_hours);
        setShopName(setup.profile.name);
        setHours(loadedHours);
        setSavedShopName(setup.profile.name);
        setSavedHours(loadedHours);
        setTwilioVoicePhone(shop.voice_phone_e164 ?? null);
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
      setEditingShop(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save shop settings");
    } finally {
      setSavingShop(false);
    }
  }

  function beginEditShop() {
    setError(null);
    setShopSuccess(null);
    setEditingShop(true);
  }

  function cancelEditShop() {
    setShopName(savedShopName);
    setHours(savedHours.map((h) => ({ ...h })));
    setEditingShop(false);
    setShopSuccess(null);
    setError(null);
  }

  function beginEditProfile() {
    setError(null);
    setProfileSuccess(null);
    setPasswordSuccess(null);
    setEditingProfile(true);
  }

  function cancelEditProfile() {
    setFullName(savedFullName);
    setProfilePhone(savedProfilePhone);
    setProfileEmail(savedProfileEmail);
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setEditingProfile(false);
    setError(null);
    setProfileSuccess(null);
    setPasswordSuccess(null);
  }

  async function onSaveProfile(e: FormEvent) {
    e.preventDefault();
    if (!editingProfile) return;
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
      setEditingProfile(false);
      setProfileSuccess("Account saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save account");
    } finally {
      setSavingProfile(false);
    }
  }

  async function onChangePassword(e: FormEvent) {
    e.preventDefault();
    if (!editingProfile) return;
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
      // Keep remembered login/register passwords in sync so Sign in still works.
      if (loadRememberedLoginPassword() !== null) {
        saveRememberedLoginPassword(newPassword);
      }
      saveRememberedRegisterPassword(newPassword);
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

  const shopDirty =
    shopName.trim() !== savedShopName.trim() || !hoursEqual(normalizeHours(hours), savedHours);
  const twilioVoice = twilioVoicePhone?.trim() || null;
  const profileDirty =
    fullName.trim() !== savedFullName.trim() ||
    profilePhone.trim() !== savedProfilePhone.trim() ||
    profileEmail.trim() !== savedProfileEmail.trim();

  if (authLoading || !session) {
    return (
      <div className="space-y-6 p-1">
        <div className="h-8 w-40 animate-pulse rounded-lg bg-black/5" />
        <div className="h-12 w-full max-w-md animate-pulse rounded-full bg-black/5" />
        <div className="h-72 animate-pulse rounded-2xl bg-black/5" />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden md:h-full">
      <header className="hero-motion shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <IconSetting className="h-5 w-5 shrink-0 text-[var(--muted)]" />
            <h1 className="page-title">Setting</h1>
          </div>

          <div
            className="inline-flex max-w-full flex-wrap gap-0.5 rounded-full border border-black/8 bg-white/80 p-0.5 shadow-[var(--shadow-soft)] backdrop-blur-sm"
            role="tablist"
            aria-label="Setting categories"
          >
            {TABS.map((t) => {
              const active = tab === t.id;
              const Icon = t.Icon;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => selectTab(t.id)}
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold leading-4 transition-colors ${
                    active
                      ? "bg-[var(--accent)] text-white"
                      : "text-[var(--muted)] hover:bg-black/[0.04] hover:text-[var(--ink)]"
                  }`}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" />
                  {t.label}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      <div
        className="flex min-h-0 flex-1 flex-col overflow-hidden touch-pan-y select-none [&_input]:select-text [&_textarea]:select-text"
        onPointerDown={onSwipePointerDown}
        onPointerUp={onSwipePointerUp}
        onPointerCancel={onSwipePointerCancel}
      >
      {error && tab !== "team" && (
        <p
          className="hero-motion-delay shrink-0 rounded-xl border border-red-200/80 bg-red-50 px-4 py-3 text-sm text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}

      {tab === "team" && <TeamPanel />}

      {tab === "shop" && (
        <section className="hero-motion-delay surface-panel flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl">
          <div className="shrink-0 border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/40 px-4 py-2.5 sm:px-6">
            <div className="flex min-w-0 items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <span
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-semibold tracking-wide text-white shadow-sm shadow-[var(--accent-glow)]"
                  aria-hidden="true"
                >
                  {profileInitials(shopName.trim() || session.shopName || "S")}
                </span>
                <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                  <h2 className="truncate text-sm font-semibold tracking-tight text-[var(--ink)]">
                    {shopName.trim() || session.shopName || "Shop"}
                  </h2>
                  <span className="inline-flex items-center gap-1 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-[var(--ink)] ring-1 ring-[var(--line)]">
                    <IconBuilding className="h-2.5 w-2.5 text-[var(--accent)]" />
                    Business
                  </span>
                  {!isOwner ? (
                    <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-medium text-[var(--muted)] ring-1 ring-[var(--line)]">
                      View only
                    </span>
                  ) : null}
                  {editingShop && shopDirty ? (
                    <span className="inline-flex items-center rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--accent)] ring-1 ring-inset ring-[var(--accent)]/20">
                      Unsaved
                    </span>
                  ) : null}
                </div>
              </div>
              {isOwner ? (
                !editingShop ? (
                  <button
                    type="button"
                    onClick={beginEditShop}
                    disabled={loading}
                    className="btn-ghost inline-flex shrink-0 items-center gap-1.5 px-3.5 py-1.5 text-xs disabled:opacity-50"
                  >
                    <IconEdit className="h-3.5 w-3.5" />
                    Change
                  </button>
                ) : (
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="submit"
                      form="shop-settings-form"
                      disabled={
                        savingShop || !shopDirty || shopName.trim().length < 2
                      }
                      className="btn-primary inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <IconSave className="h-3.5 w-3.5" />
                      {savingShop ? "Saving…" : "Save"}
                    </button>
                    <button
                      type="button"
                      onClick={cancelEditShop}
                      disabled={savingShop}
                      className="btn-ghost inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs disabled:opacity-50"
                    >
                      <IconX className="h-3.5 w-3.5" />
                      Cancel
                    </button>
                  </div>
                )
              ) : null}
            </div>
          </div>

          <div className="asa-scroll min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6">
            {shopSuccess && (
              <p
                className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                role="status"
              >
                {shopSuccess}
              </p>
            )}

            {loading ? (
              <div className="space-y-4">
                <div className="h-11 animate-pulse rounded-md bg-black/5" />
                <div className="h-28 animate-pulse rounded-xl bg-black/5" />
                <div className="h-48 animate-pulse rounded-xl bg-black/5" />
              </div>
            ) : (
              <>
                <section className="space-y-3">
                  <form
                    id="shop-settings-form"
                    onSubmit={onSaveShop}
                    className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 sm:grid-cols-2 sm:gap-3 [&>*]:min-w-0"
                  >
                    <ProfileField
                      label="Shop name"
                      icon={<IconBuilding />}
                      value={shopName}
                      onChange={setShopName}
                      required
                      disabled={!isOwner || !editingShop || savingShop}
                      minLength={2}
                      maxLength={255}
                    />
                    <label className="block w-[7.25rem] space-y-1.5 sm:w-auto">
                      <span className="inline-flex items-center gap-1.5 text-sm font-medium">
                        <span className="text-[var(--muted)]">
                          <IconShield />
                        </span>
                        Access
                      </span>
                      <input
                        type="text"
                        value={isOwner ? "Owner" : "Team"}
                        disabled
                        title={isOwner ? "Owner — can edit" : "Team — view only"}
                        className="w-full rounded-md border border-[var(--line)] bg-[var(--background)] px-2 py-2 text-xs text-[var(--muted)] outline-none sm:hidden"
                      />
                      <input
                        type="text"
                        value={isOwner ? "Owner — can edit" : "Team — view only"}
                        disabled
                        className="hidden w-full rounded-md border border-[var(--line)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--muted)] outline-none sm:block"
                      />
                    </label>
                  </form>
                </section>

                <section className="space-y-2">
                  <div>
                    <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold">
                      <span className="text-[var(--muted)]">
                        <IconPhone />
                      </span>
                      AI phone number
                    </h3>
                    <p className="mt-0.5 text-xs text-[var(--muted)]">
                      Forward your shop phone to this number so inbound calls can be
                      handled by AI.
                    </p>
                  </div>

                  {!twilioVoice ? (
                    <div className="rounded-xl border border-dashed border-[var(--line)] bg-[var(--background)]/50 px-4 py-3 text-center">
                      <p className="text-sm font-medium">No number assigned yet</p>
                      <p className="mt-0.5 text-xs text-[var(--muted)]">
                        Contact support if you need Voice AI for this shop.
                      </p>
                    </div>
                  ) : (
                    <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--line)] bg-[var(--panel)] px-3 py-2 shadow-[var(--shadow-soft)]">
                      <p className="font-mono text-sm font-medium tracking-tight text-[var(--ink)]">
                        {formatPhoneInput(twilioVoice)}
                      </p>
                      <button
                        type="button"
                        className="btn-ghost inline-flex items-center gap-1.5 px-2.5 py-1 text-xs"
                        onClick={() => void navigator.clipboard.writeText(twilioVoice)}
                      >
                        <IconCopy className="h-3.5 w-3.5" />
                        Copy
                      </button>
                    </div>
                  )}
                </section>

                <section className="space-y-4">
                  <div>
                    <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold">
                      <span className="text-[var(--muted)]">
                        <IconClock />
                      </span>
                      Business hours
                    </h3>
                  </div>

                  <div className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)]">
                    <div className="hidden items-center gap-3 border-b border-[var(--line)] bg-[var(--background)]/60 px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)] sm:grid sm:grid-cols-[8.5rem_1fr_auto]">
                      <span>Day</span>
                      <span>Hours</span>
                      <span className="text-right">Status</span>
                    </div>
                    {hours.map((h, idx) => {
                      const canEdit = isOwner && editingShop && !savingShop;
                      const open = !h.closed;
                      const dayName = WEEKDAY_NAMES[h.weekday];
                      return (
                        <div
                          key={h.weekday}
                          className={`grid grid-cols-[3.25rem_minmax(0,1fr)_auto] items-center gap-x-2 px-3 py-2.5 transition-colors sm:grid-cols-[8.5rem_minmax(0,1fr)_auto] sm:gap-x-3 sm:px-4 sm:py-3.5 ${
                            idx > 0 ? "border-t border-[var(--line)]" : ""
                          } ${h.closed ? "bg-[var(--background)]/50" : "bg-white/40"}`}
                        >
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold tracking-tight text-[var(--ink)]">
                              <span className="sm:hidden">{dayName.slice(0, 3)}</span>
                              <span className="hidden sm:inline">{dayName}</span>
                            </p>
                          </div>

                          <div className="min-w-0">
                            {h.closed ? (
                              <span className="inline-flex items-center rounded-full bg-black/[0.04] px-2 py-1 text-[11px] font-medium text-[var(--muted)] ring-1 ring-inset ring-black/5 sm:px-2.5 sm:text-xs">
                                Closed
                              </span>
                            ) : canEdit ? (
                              <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-1 sm:gap-1.5">
                                <input
                                  type="time"
                                  value={h.open_time}
                                  disabled={!canEdit}
                                  aria-label={`${dayName} open`}
                                  onChange={(e) =>
                                    updateHour(h.weekday, { open_time: e.target.value })
                                  }
                                  className="min-w-0 w-full rounded-md border border-[var(--line)] bg-white px-1 py-1.5 text-xs tabular-nums outline-none ring-[var(--accent)] focus:ring-2 disabled:cursor-not-allowed disabled:opacity-40 sm:px-2.5 sm:text-sm"
                                />
                                <span className="shrink-0 text-xs font-medium text-[var(--muted)]" aria-hidden>
                                  –
                                </span>
                                <input
                                  type="time"
                                  value={h.close_time}
                                  disabled={!canEdit}
                                  aria-label={`${dayName} close`}
                                  onChange={(e) =>
                                    updateHour(h.weekday, { close_time: e.target.value })
                                  }
                                  className="min-w-0 w-full rounded-md border border-[var(--line)] bg-white px-1 py-1.5 text-xs tabular-nums outline-none ring-[var(--accent)] focus:ring-2 disabled:cursor-not-allowed disabled:opacity-40 sm:px-2.5 sm:text-sm"
                                />
                              </div>
                            ) : (
                              <p className="truncate text-xs font-medium tabular-nums tracking-tight text-[var(--ink)] sm:text-sm">
                                <span>{formatHourLabel(h.open_time)}</span>
                                <span className="mx-1 text-[var(--muted)] sm:mx-2">–</span>
                                <span>{formatHourLabel(h.close_time)}</span>
                              </p>
                            )}
                          </div>

                          <button
                            type="button"
                            role="switch"
                            aria-checked={open}
                            aria-label={`${dayName} ${open ? "open" : "closed"}`}
                            disabled={!canEdit}
                            onClick={() => updateHour(h.weekday, { closed: open })}
                            className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-0.5 py-1 transition disabled:cursor-not-allowed sm:gap-2 sm:px-1 ${
                              canEdit ? "hover:opacity-90" : "opacity-90"
                            }`}
                          >
                            <span
                              className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
                                open
                                  ? "bg-[var(--accent)] shadow-sm shadow-[var(--accent-glow)]"
                                  : "bg-black/15"
                              }`}
                            >
                              <span
                                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all duration-200 ${
                                  open ? "left-[1.125rem]" : "left-0.5"
                                }`}
                              />
                            </span>
                            <span
                              className={`hidden min-w-[2.75rem] text-left text-xs font-semibold sm:inline ${
                                open ? "text-[var(--ink)]" : "text-[var(--muted)]"
                              }`}
                            >
                              {open ? "Open" : "Closed"}
                            </span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </section>

                <ServicesPanel embedded editing={editingShop} />
              </>
            )}
          </div>
        </section>
      )}

      {tab === "account" && (
        <section className="hero-motion-delay surface-panel flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl">
          <div className="shrink-0 border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/40 px-4 py-2.5 sm:px-6">
            <div className="flex min-w-0 items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2.5">
                <span
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-xs font-semibold tracking-wide text-white shadow-sm shadow-[var(--accent-glow)]"
                  aria-hidden="true"
                >
                  {profileInitials(fullName.trim() || session.fullName || "?")}
                </span>
                <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                  <h2 className="truncate text-sm font-semibold tracking-tight text-[var(--ink)]">
                    {fullName.trim() || session.fullName || "Your account"}
                  </h2>
                  <span className="inline-flex items-center gap-1 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold text-[var(--ink)] ring-1 ring-[var(--line)]">
                    <IconShield className="h-2.5 w-2.5 text-[var(--accent)]" />
                    {ROLE_LABELS[session.role]}
                  </span>
                  {session.shopName ? (
                    <span className="rounded-full bg-white/70 px-2 py-0.5 text-[10px] font-medium text-[var(--muted)] ring-1 ring-[var(--line)]">
                      {session.shopName}
                    </span>
                  ) : null}
                  {editingProfile && profileDirty ? (
                    <span className="inline-flex items-center rounded-full bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--accent)] ring-1 ring-inset ring-[var(--accent)]/20">
                      Unsaved
                    </span>
                  ) : null}
                </div>
              </div>
              {!editingProfile ? (
                <button
                  type="button"
                  onClick={beginEditProfile}
                  className="btn-ghost inline-flex shrink-0 items-center gap-1.5 px-3.5 py-1.5 text-xs"
                >
                  <IconEdit className="h-3.5 w-3.5" />
                  Change
                </button>
              ) : (
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    type="submit"
                    form="account-profile-form"
                    disabled={savingProfile || !fullName.trim() || !profileDirty}
                    className="btn-primary inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <IconSave className="h-3.5 w-3.5" />
                    {savingProfile ? "Saving…" : "Save"}
                  </button>
                  <button
                    type="button"
                    onClick={cancelEditProfile}
                    disabled={savingProfile}
                    className="btn-ghost inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs disabled:opacity-50"
                  >
                    <IconX className="h-3.5 w-3.5" />
                    Cancel
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="asa-scroll min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain px-4 py-5 sm:px-6">
            {profileSuccess && (
              <p
                className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                role="status"
              >
                {profileSuccess}
              </p>
            )}

            <section className="space-y-3">
              <form
                id="account-profile-form"
                onSubmit={onSaveProfile}
                className="grid grid-cols-2 gap-3"
              >
                <ProfileField
                  label="Name"
                  icon={<IconUser />}
                  value={fullName}
                  onChange={setFullName}
                  required
                  disabled={!editingProfile || savingProfile}
                  minLength={1}
                  maxLength={255}
                />
                <ProfileField
                  label="Phone"
                  icon={<IconPhone />}
                  type="tel"
                  value={profilePhone}
                  onChange={(v) => setProfilePhone(formatPhoneInput(v))}
                  disabled={!editingProfile || savingProfile}
                  placeholder={PHONE_PLACEHOLDER}
                  maxLength={16}
                />
                <ProfileField
                  label="Email"
                  icon={<IconMail />}
                  type="email"
                  value={profileEmail}
                  onChange={setProfileEmail}
                  disabled={!editingProfile || savingProfile}
                  placeholder="you@example.com"
                  maxLength={320}
                />
                <label className="block space-y-1.5">
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium">
                    <span className="text-[var(--muted)]">
                      <IconShield />
                    </span>
                    Role
                  </span>
                  <input
                    type="text"
                    value={ROLE_LABELS[session.role]}
                    disabled
                    className="w-full rounded-md border border-[var(--line)] bg-[var(--background)] px-3 py-2 text-sm text-[var(--muted)] outline-none"
                  />
                </label>
              </form>
            </section>

            <section className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="inline-flex items-center gap-1.5 text-sm font-semibold">
                    <span className="text-[var(--muted)]">
                      <IconLock />
                    </span>
                    Password
                  </h3>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    Update your password (at least 8 characters)
                  </p>
                </div>
              </div>

              <form
                onSubmit={onChangePassword}
                className={`rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 shadow-[var(--shadow-soft)] sm:p-5 ${
                  !editingProfile ? "opacity-60" : ""
                }`}
              >
                {passwordSuccess && (
                  <p
                    className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                    role="status"
                  >
                    {passwordSuccess}
                  </p>
                )}

                <div className="grid max-w-xl gap-3 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <PasswordField
                      label="Current password"
                      value={currentPassword}
                      onChange={setCurrentPassword}
                      required
                      disabled={!editingProfile || savingPassword}
                      autoComplete="current-password"
                    />
                  </div>
                  <PasswordField
                    label="New password"
                    value={newPassword}
                    onChange={setNewPassword}
                    required
                    minLength={8}
                    disabled={!editingProfile || savingPassword}
                    autoComplete="new-password"
                  />
                  <PasswordField
                    label="Confirm new password"
                    value={confirmPassword}
                    onChange={setConfirmPassword}
                    required
                    minLength={8}
                    disabled={!editingProfile || savingPassword}
                    autoComplete="new-password"
                  />
                </div>
                {editingProfile ? (
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <button
                      type="submit"
                      disabled={
                        savingPassword ||
                        !currentPassword ||
                        newPassword.length < 8 ||
                        confirmPassword.length < 8
                      }
                      className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <IconSave />
                      {savingPassword ? "Saving…" : "Update password"}
                    </button>
                  </div>
                ) : null}
              </form>
            </section>
          </div>
        </section>
      )}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-6 p-1">
          <div className="h-8 w-40 animate-pulse rounded-lg bg-black/5" />
          <div className="h-72 animate-pulse rounded-2xl bg-black/5" />
        </div>
      }
    >
      <SettingsContent />
    </Suspense>
  );
}
