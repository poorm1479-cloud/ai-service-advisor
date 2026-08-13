"use client";

import Link from "next/link";
import {
  FormEvent,
  PointerEvent as ReactPointerEvent,
  ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  addRepairHistory,
  Communication,
  createVehicle,
  CustomerDetail,
  deleteCommunication,
  deleteCustomer,
  deleteRepairHistory,
  deleteVehicle,
  getCustomerDetail,
  RepairHistory,
  updateCustomer,
  updateVehicle,
  Vehicle,
} from "@/lib/crm";
import { useAuth } from "@/lib/auth";
import dynamic from "next/dynamic";
import { formatPhoneInput, PHONE_PLACEHOLDER, phonesMatch } from "@/lib/phone";
import { deleteVoiceCall, listVoiceCalls, VoiceCall } from "@/lib/calls";
import {
  deleteSmsConversation,
  listSmsConversations,
  SmsConversation,
} from "@/lib/sms";
import {
  formatPrice,
  listShopServices,
  ShopService,
} from "@/lib/shopSetup";
import { vinAssist } from "@/lib/walkin";

/** VIN scanner pulls zxing/tesseract — load only when Add/Edit vehicle opens. */
const VinInput = dynamic(
  () => import("@/components/VinInput").then((m) => m.VinInput),
  {
    ssr: false,
    loading: () => (
      <div className="space-y-2 sm:col-span-2 lg:col-span-2">
        <div className="h-10 animate-pulse rounded-lg bg-[var(--background)]" />
      </div>
    ),
  },
);

const DETAIL_TABS = [
  { id: "profile", label: "Profile" },
  { id: "repairs", label: "Repair history" },
  { id: "calls", label: "Calls" },
] as const;

/** Minimum horizontal drag distance (px) to change detail tabs. */
const TAB_SWIPE_THRESHOLD_PX = 56;

type DetailTab = (typeof DETAIL_TABS)[number]["id"];

function parseDetailTab(value: string | null): DetailTab {
  if (value === "calls" || value === "conversations") return "calls";
  if (value === "repairs" || value === "profile") {
    return value;
  }
  return "profile";
}

const VIN_ALPHABET = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789";

/** Temporary VIN when only plate/year/make/model is known — valid charset for API. */
function makeTempVin(): string {
  const stamp = Date.now().toString(36).toUpperCase().replace(/[IOQ]/g, "");
  let out = `TMP${stamp}`;
  while (out.length < 17) {
    out += VIN_ALPHABET[Math.floor(Math.random() * VIN_ALPHABET.length)];
  }
  return out.slice(0, 17);
}

function vehicleLabel(v: Vehicle): string {
  return `${v.year} ${v.make} ${v.model}`.trim();
}

function customerInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function IconCar({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M5 17h14v-5l-1.5-4.5A2 2 0 0 0 15.6 6H8.4a2 2 0 0 0-1.9 1.5L5 12v5Z" />
      <path d="M5 17H3v-2" />
      <path d="M21 17h-2v-2" />
      <circle cx="7.5" cy="17.5" r="1.5" />
      <circle cx="16.5" cy="17.5" r="1.5" />
    </svg>
  );
}

function IconCarPlus({ className = "h-5 w-5" }: { className?: string }) {
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
      {/* Car left, vertically centered with + (same + as IconUserPlus) */}
      <path d="M1.5 13.5h12v-3.2L12.3 7A1.5 1.5 0 0 0 10.9 6H5.1A1.5 1.5 0 0 0 3.7 7L2.3 10.3v3.2Z" />
      <path d="M1.5 13.5H.25v-1.4" />
      <path d="M13.5 13.5h-1.25v-1.4" />
      <circle cx="4.25" cy="14" r="1.2" />
      <circle cx="10.75" cy="14" r="1.2" />
      <path d="M19 8v6M16 11h6" />
    </svg>
  );
}

function IconPlus({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.25"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 5v14M5 12h14" />
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

function IconMapPin({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
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

function IconCancel({ className = "h-4 w-4" }: { className?: string }) {
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

function IconWrench({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z" />
    </svg>
  );
}

function IconWrenchPlus({ className = "h-5 w-5" }: { className?: string }) {
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
      {/* Wrench left, + right — extra gap between glyph and plus */}
      <path d="M8.8 7.2a.7.7 0 0 0 0 1l1.05 1.05a.7.7 0 0 0 1 0l2.05-2.05a3.5 3.5 0 0 1-4.6 4.6L3.25 16a1.2 1.2 0 0 1-1.7-1.7l4.05-4.05a3.5 3.5 0 0 1 4.6-4.6L8.8 7.2Z" />
      <path d="M20 8v6M17 11h6" />
    </svg>
  );
}

function IconTrash({ className = "h-4 w-4" }: { className?: string }) {
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

function IconMessage({ className = "h-3.5 w-3.5" }: { className?: string }) {
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
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function IconChevronRight({ className = "h-4 w-4" }: { className?: string }) {
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
      <path d="m9 18 6-6-6-6" />
    </svg>
  );
}

function formatConversationWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Call duration: recording length, else ended−started. */
function formatCallDuration(call: VoiceCall): string | null {
  let sec = call.recording_duration_sec;
  if (sec == null || sec < 0) {
    if (call.started_at && call.ended_at) {
      const start = new Date(call.started_at).getTime();
      const end = new Date(call.ended_at).getTime();
      if (!Number.isNaN(start) && !Number.isNaN(end) && end >= start) {
        sec = Math.round((end - start) / 1000);
      }
    }
  }
  if (sec == null || sec < 0) return null;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}

function channelLabel(channel: Communication["channel"]): string {
  switch (channel) {
    case "sms":
      return "SMS";
    case "email":
      return "Email";
    case "facebook":
      return "Facebook";
    case "phone":
      return "Phone";
    default:
      return channel;
  }
}

type RepairWithVehicle = RepairHistory & { vehicle_label: string };

type DeleteConversationTarget =
  | { kind: "call"; call: VoiceCall }
  | { kind: "sms"; sms: SmsConversation }
  | { kind: "comm"; comm: Communication };

type RepairServiceLine = {
  key: string;
  serviceId: string; // catalog id, or "" when custom
  name: string;
  cost: string;
};

function newRepairLineKey(): string {
  return `rl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function emptyRepairLine(partial?: Partial<RepairServiceLine>): RepairServiceLine {
  return {
    key: newRepairLineKey(),
    serviceId: "",
    name: "",
    cost: "",
    ...partial,
  };
}

/** Local calendar date as YYYY-MM-DD for `<input type="date">`. */
function todayDateInputValue(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Convert YYYY-MM-DD to ISO using local noon (stable across timezones when shown as a date). */
function dateInputToIso(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  if (!y || !m || !d) return new Date().toISOString();
  return new Date(y, m - 1, d, 12, 0, 0).toISOString();
}

export function CustomerDetailContent({
  customerId: customerIdProp,
  embedded = false,
  onBack,
  onDeleted,
}: {
  customerId?: string;
  embedded?: boolean;
  onBack?: () => void;
  onDeleted?: () => void;
} = {}) {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const customerId = customerIdProp ?? params.id;
  const { session, loading: authLoading } = useAuth();
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [repairs, setRepairs] = useState<RepairWithVehicle[]>([]);
  const [voiceCalls, setVoiceCalls] = useState<VoiceCall[]>([]);
  const [smsConversations, setSmsConversations] = useState<SmsConversation[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deletingCustomer, setDeletingCustomer] = useState(false);
  const [deleteCustomerOpen, setDeleteCustomerOpen] = useState(false);
  const [tab, setTab] = useState<DetailTab>(() =>
    parseDetailTab(searchParams.get("tab")),
  );

  useEffect(() => {
    setTab(parseDetailTab(searchParams.get("tab")));
  }, [searchParams]);

  const selectTab = useCallback(
    (next: DetailTab) => {
      setTab(next);
      const nextParams = new URLSearchParams(searchParams.toString());
      if (next === "profile") {
        nextParams.delete("tab");
      } else {
        nextParams.set("tab", next);
      }
      const qs = nextParams.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  /** Horizontal click-drag / swipe switches adjacent detail tabs. */
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

      const idx = DETAIL_TABS.findIndex((t) => t.id === tab);
      if (idx < 0) return;
      if (dx < 0 && idx < DETAIL_TABS.length - 1) {
        selectTab(DETAIL_TABS[idx + 1].id);
      } else if (dx > 0 && idx > 0) {
        selectTab(DETAIL_TABS[idx - 1].id);
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

  const [editName, setEditName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editAddress, setEditAddress] = useState("");
  const [profileEditing, setProfileEditing] = useState(false);

  const [vin, setVin] = useState("");
  const [plate, setPlate] = useState("");
  const [year, setYear] = useState("2018");
  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [mileage, setMileage] = useState("0");
  const [vehicleModal, setVehicleModal] = useState<"add" | "edit" | null>(null);
  const [editingVehicleId, setEditingVehicleId] = useState<string | null>(null);
  const [vehicleSaving, setVehicleSaving] = useState(false);
  const [deletingVehicleId, setDeletingVehicleId] = useState<string | null>(null);
  const [deleteVehicleTarget, setDeleteVehicleTarget] = useState<Vehicle | null>(null);
  const [deletingRepairId, setDeletingRepairId] = useState<string | null>(null);
  const [deleteRepairTarget, setDeleteRepairTarget] = useState<RepairWithVehicle | null>(null);
  const [deleteConversationTarget, setDeleteConversationTarget] =
    useState<DeleteConversationTarget | null>(null);
  const [deletingConversation, setDeletingConversation] = useState(false);
  const [repairModalOpen, setRepairModalOpen] = useState(false);
  const [repairSaving, setRepairSaving] = useState(false);
  const [shopServices, setShopServices] = useState<ShopService[]>([]);
  const [repairVehicleId, setRepairVehicleId] = useState("");
  const [repairLines, setRepairLines] = useState<RepairServiceLine[]>([
    emptyRepairLine(),
  ]);
  const [repairDescription, setRepairDescription] = useState("");
  const [repairRecommendation, setRepairRecommendation] = useState("");
  const [repairDate, setRepairDate] = useState(todayDateInputValue);
  /** After adding a vehicle from the Repair tab, open the repair modal. */
  const [openRepairAfterVehicle, setOpenRepairAfterVehicle] = useState(false);
  const [vinStatus, setVinStatus] = useState<string | null>(null);
  const [vinLooking, setVinLooking] = useState(false);
  const vinAssistSeq = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setVoiceCalls([]);
    setSmsConversations([]);
    try {
      const data = await getCustomerDetail(customerId);
      const vehicleById = new Map(data.vehicles.map((v) => [v.id, v]));
      const flatRepairs = (data.repair_history ?? [])
        .map((r) => {
          const v = vehicleById.get(r.vehicle_id);
          return {
            ...r,
            vehicle_label: v ? vehicleLabel(v) : "Vehicle",
          };
        })
        .sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
          return tb - ta;
        });

      setDetail(data);
      setRepairs(flatRepairs);
      setEditName(data.customer.name);
      setEditPhone(formatPhoneInput(data.customer.phone ?? ""));
      setEditEmail(data.customer.email ?? "");
      setEditAddress(data.customer.address ?? "");
      setLoading(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customer");
      setLoading(false);
    }
  }, [customerId]);

  const loadConversations = useCallback(async () => {
    if (!detail) return;
    setConversationsLoading(true);
    // Match Calls by customer_id OR phone (many calls/SMS lack customer_id).
    const customerPhone = detail.customer.phone;
    const belongsToCustomer = (opts: {
      customer_id: string | null;
      phone: string | null | undefined;
    }) =>
      opts.customer_id === customerId ||
      (!!customerPhone && phonesMatch(opts.phone, customerPhone));

    try {
      const [callsAll, smsAll] = await Promise.all([
        listVoiceCalls().catch(() => [] as VoiceCall[]),
        listSmsConversations().catch(() => [] as SmsConversation[]),
      ]);
      setVoiceCalls(
        callsAll.filter((c) =>
          belongsToCustomer({
            customer_id: c.customer_id,
            phone: c.caller_phone,
          }),
        ),
      );
      setSmsConversations(
        smsAll.filter((c) =>
          belongsToCustomer({
            customer_id: c.customer_id,
            phone: c.customer_phone,
          }),
        ),
      );
    } finally {
      setConversationsLoading(false);
    }
  }, [customerId, detail]);

  useEffect(() => {
    if (!authLoading && session && customerId) {
      void load();
    }
  }, [authLoading, session, customerId, load]);

  // Calls tab only — avoid listing all calls/SMS on every profile open.
  useEffect(() => {
    if (tab !== "calls" || !detail || authLoading || !session) return;
    void loadConversations();
  }, [tab, detail, authLoading, session, loadConversations]);

  useEffect(() => {
    if (authLoading || !session) return;
    let cancelled = false;
    void listShopServices(true)
      .then((list) => {
        if (!cancelled) setShopServices(list);
      })
      .catch(() => {
        if (!cancelled) setShopServices([]);
      });
    return () => {
      cancelled = true;
    };
  }, [authLoading, session]);

  const profileDirty = useMemo(() => {
    if (!detail) return false;
    const c = detail.customer;
    return (
      editName.trim() !== (c.name ?? "").trim() ||
      editPhone !== formatPhoneInput(c.phone ?? "") ||
      editEmail.trim() !== (c.email ?? "").trim() ||
      editAddress.trim() !== (c.address ?? "").trim()
    );
  }, [detail, editName, editPhone, editEmail, editAddress]);

  const vehicleDirty = useMemo(() => {
    if (vehicleModal !== "edit" || !editingVehicleId || !detail) return false;
    const v = detail.vehicles.find((x) => x.id === editingVehicleId);
    if (!v) return false;
    const cleanedVin = vin.replace(/[\s-]/g, "").toUpperCase();
    const originalVin = v.vin.replace(/[\s-]/g, "").toUpperCase();
    return (
      cleanedVin !== originalVin ||
      plate.trim() !== (v.license_plate ?? "").trim() ||
      year.trim() !== String(v.year) ||
      make.trim() !== (v.make ?? "").trim() ||
      model.trim() !== (v.model ?? "").trim() ||
      Number(mileage || 0) !== v.mileage
    );
  }, [
    vehicleModal,
    editingVehicleId,
    detail,
    vin,
    plate,
    year,
    make,
    model,
    mileage,
  ]);

  const conversationTimeline = useMemo(() => {
    type Item =
      | { kind: "call"; id: string; at: number; call: VoiceCall }
      | { kind: "sms"; id: string; at: number; sms: SmsConversation }
      | { kind: "comm"; id: string; at: number; comm: Communication };

    const items: Item[] = [];
    for (const call of voiceCalls) {
      const raw = call.started_at || call.created_at;
      const at = raw ? new Date(raw).getTime() : 0;
      items.push({
        kind: "call",
        id: `call-${call.id}`,
        at: Number.isFinite(at) ? at : 0,
        call,
      });
    }
    for (const sms of smsConversations) {
      const raw = sms.last_message_at || sms.created_at;
      const at = raw ? new Date(raw).getTime() : 0;
      items.push({
        kind: "sms",
        id: `sms-${sms.id}`,
        at: Number.isFinite(at) ? at : 0,
        sms,
      });
    }
    for (const comm of detail?.communications ?? []) {
      // Skip SMS CRM rows when the thread already appears as an SmsConversation
      if (
        comm.channel === "sms" &&
        smsConversations.length > 0
      ) {
        continue;
      }
      const at = comm.created_at ? new Date(comm.created_at).getTime() : 0;
      items.push({
        kind: "comm",
        id: `comm-${comm.id}`,
        at: Number.isFinite(at) ? at : 0,
        comm,
      });
    }
    items.sort((a, b) => b.at - a.at);
    return items;
  }, [voiceCalls, smsConversations, detail?.communications]);

  const otherMessageCount = useMemo(() => {
    const comms = detail?.communications ?? [];
    if (smsConversations.length > 0) {
      return comms.filter((c) => c.channel !== "sms").length;
    }
    return comms.length;
  }, [detail?.communications, smsConversations.length]);

  useEffect(() => {
    if (profileDirty) setSuccess(null);
  }, [profileDirty]);

  function resetProfileFields() {
    if (!detail) return;
    setEditName(detail.customer.name);
    setEditPhone(formatPhoneInput(detail.customer.phone ?? ""));
    setEditEmail(detail.customer.email ?? "");
    setEditAddress(detail.customer.address ?? "");
  }

  function cancelProfileEdit() {
    resetProfileFields();
    setProfileEditing(false);
    setError(null);
  }

  async function onSaveCustomer(e: FormEvent) {
    e.preventDefault();
    if (!profileEditing || !profileDirty) return;
    setError(null);
    setSuccess(null);
    try {
      await updateCustomer(customerId, {
        name: editName.trim(),
        phone: editPhone.trim() || null,
        email: editEmail.trim() || null,
        address: editAddress.trim() || null,
      });
      await load();
      setProfileEditing(false);
      setSuccess("Customer profile updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  function resetVehicleForm() {
    vinAssistSeq.current += 1;
    setVin("");
    setPlate("");
    setYear("");
    setMake("");
    setModel("");
    setMileage("");
    setEditingVehicleId(null);
    setVinStatus(null);
    setVinLooking(false);
  }

  useEffect(() => {
    if (!vehicleModal) return;

    const cleaned = vin.replace(/[\s-]/g, "").toUpperCase();
    if (cleaned.length !== 17) {
      setVinStatus(null);
      setVinLooking(false);
      return;
    }

    // Edit modal opens with a known VIN — skip re-lookup until the user changes it.
    if (
      vehicleModal === "edit" &&
      editingVehicleId &&
      detail?.vehicles.some(
        (v) =>
          v.id === editingVehicleId &&
          v.vin.replace(/[\s-]/g, "").toUpperCase() === cleaned,
      )
    ) {
      return;
    }

    const seq = ++vinAssistSeq.current;
    const timer = window.setTimeout(() => {
      void (async () => {
        setVinLooking(true);
        try {
          const assist = await vinAssist(cleaned);
          if (seq !== vinAssistSeq.current) return;

          if (assist.existing) {
            const v = assist.existing;
            setVin(v.vin);
            setPlate(v.license_plate ?? "");
            setYear(String(v.year));
            setMake(v.make);
            setModel(v.model);
            setMileage(String(v.mileage));
          } else if (assist.decoded) {
            const d = assist.decoded;
            setVin(d.vin);
            setYear(String(d.year));
            setMake(d.make);
            setModel(d.model);
          }
          setVinStatus(assist.message);
        } catch (err) {
          if (seq !== vinAssistSeq.current) return;
          setVinStatus(err instanceof Error ? err.message : "VIN lookup failed");
        } finally {
          if (seq === vinAssistSeq.current) setVinLooking(false);
        }
      })();
    }, 350);

    return () => window.clearTimeout(timer);
  }, [vin, vehicleModal, editingVehicleId, detail?.vehicles]);

  function openAddVehicleModal() {
    resetVehicleForm();
    setError(null);
    setSuccess(null);
    setVehicleModal("add");
  }

  function openEditVehicleModal(v: Vehicle) {
    setOpenRepairAfterVehicle(false);
    setEditingVehicleId(v.id);
    setVin(v.vin);
    setPlate(v.license_plate ?? "");
    setYear(String(v.year));
    setMake(v.make);
    setModel(v.model);
    setMileage(String(v.mileage));
    setError(null);
    setSuccess(null);
    setVehicleModal("edit");
  }

  function closeVehicleModal() {
    if (vehicleSaving) return;
    setVehicleModal(null);
    setOpenRepairAfterVehicle(false);
    resetVehicleForm();
    // Vehicle form errors are shown inside the modal only — clear so they
    // do not linger on the customer detail page after close.
    setError(null);
  }

  useEffect(() => {
    if (!vehicleModal) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (vehicleSaving || deletingVehicleId) return;
      e.preventDefault();
      setVehicleModal(null);
      setOpenRepairAfterVehicle(false);
      vinAssistSeq.current += 1;
      setVin("");
      setPlate("");
      setYear("");
      setMake("");
      setModel("");
      setMileage("");
      setEditingVehicleId(null);
      setVinStatus(null);
      setVinLooking(false);
      setError(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [vehicleModal, vehicleSaving, deletingVehicleId]);

  async function onSaveVehicle(e: FormEvent) {
    e.preventDefault();
    if (vehicleModal === "edit" && !vehicleDirty) return;
    setError(null);
    setSuccess(null);
    setVehicleSaving(true);
    try {
      let createdVehicle: Vehicle | null = null;
      if (vehicleModal === "edit" && editingVehicleId) {
        const cleanedVin = vin.replace(/[\s-]/g, "").toUpperCase();
        if (cleanedVin.length !== 17) {
          throw new Error("VIN must be 17 characters");
        }
        if (!make.trim() || !model.trim() || !year.trim()) {
          throw new Error("Year, make, and model are required");
        }
        await updateVehicle(editingVehicleId, {
          vin: cleanedVin,
          license_plate: plate.trim() || null,
          year: Number(year),
          make: make.trim(),
          model: model.trim(),
          mileage: Number(mileage || 0),
        });
        setSuccess("Vehicle updated.");
      } else {
        const hasAny =
          Boolean(vin.trim()) ||
          Boolean(plate.trim()) ||
          Boolean(year.trim()) ||
          Boolean(make.trim()) ||
          Boolean(model.trim()) ||
          Boolean(mileage.trim());
        if (!hasAny) {
          throw new Error("Enter at least one vehicle detail to add");
        }

        const cleanedVin = vin.replace(/[\s-]/g, "").toUpperCase();
        if (cleanedVin && cleanedVin.length !== 17) {
          throw new Error("VIN must be 17 characters, or leave it blank");
        }

        const yearNum = year.trim() ? Number(year) : new Date().getFullYear();
        if (!Number.isFinite(yearNum) || yearNum < 1900 || yearNum > 2100) {
          throw new Error("Year must be between 1900 and 2100");
        }

        const mileageNum = mileage.trim() ? Number(mileage) : 0;
        if (!Number.isFinite(mileageNum) || mileageNum < 0) {
          throw new Error("Mileage must be a non-negative number");
        }

        createdVehicle = await createVehicle(customerId, {
          vin: cleanedVin || makeTempVin(),
          license_plate: plate.trim() || undefined,
          year: yearNum,
          make: make.trim() || "Unknown",
          model: model.trim() || "Unknown",
          mileage: mileageNum,
        });
        setSuccess("Vehicle added.");
      }
      const continueToRepair = openRepairAfterVehicle && createdVehicle !== null;
      setVehicleModal(null);
      setOpenRepairAfterVehicle(false);
      resetVehicleForm();
      await load();
      if (continueToRepair && createdVehicle) {
        resetRepairForm([createdVehicle]);
        setRepairModalOpen(true);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : vehicleModal === "edit"
            ? "Vehicle update failed"
            : "Vehicle create failed",
      );
    } finally {
      setVehicleSaving(false);
    }
  }

  async function onConfirmDeleteVehicle() {
    const v = deleteVehicleTarget;
    if (!v) return;
    setDeletingVehicleId(v.id);
    setError(null);
    setSuccess(null);
    try {
      await deleteVehicle(v.id);
      if (editingVehicleId === v.id) {
        setVehicleModal(null);
        resetVehicleForm();
      }
      setDeleteVehicleTarget(null);
      setSuccess("Vehicle deleted.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete vehicle");
    } finally {
      setDeletingVehicleId(null);
    }
  }

  async function onConfirmDeleteRepair() {
    const r = deleteRepairTarget;
    if (!r) return;
    setDeletingRepairId(r.id);
    setError(null);
    setSuccess(null);
    try {
      await deleteRepairHistory(r.vehicle_id, r.id);
      setDeleteRepairTarget(null);
      setSuccess("Repair history deleted.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete repair history");
    } finally {
      setDeletingRepairId(null);
    }
  }

  async function onConfirmDeleteConversation() {
    const target = deleteConversationTarget;
    if (!target) return;
    setDeletingConversation(true);
    setError(null);
    setSuccess(null);
    try {
      if (target.kind === "call") {
        await deleteVoiceCall(target.call.id);
        setVoiceCalls((prev) => prev.filter((c) => c.id !== target.call.id));
        setSuccess("Call history deleted.");
      } else if (target.kind === "sms") {
        await deleteSmsConversation(target.sms.id);
        setSmsConversations((prev) =>
          prev.filter((c) => c.id !== target.sms.id),
        );
        setSuccess("SMS conversation deleted.");
      } else {
        await deleteCommunication(customerId, target.comm.id);
        setDetail((prev) =>
          prev
            ? {
                ...prev,
                communications: prev.communications.filter(
                  (c) => c.id !== target.comm.id,
                ),
              }
            : prev,
        );
        setSuccess("Message deleted.");
      }
      setDeleteConversationTarget(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete conversation",
      );
    } finally {
      setDeletingConversation(false);
    }
  }

  function resetRepairForm(vehicles?: Vehicle[]) {
    const list = vehicles ?? detail?.vehicles ?? [];
    setRepairVehicleId(list[0]?.id ?? "");
    setRepairLines([emptyRepairLine()]);
    setRepairDescription("");
    setRepairRecommendation("");
    setRepairDate(todayDateInputValue());
  }

  function openAddRepairModal() {
    setError(null);
    setSuccess(null);
    if (!detail || detail.vehicles.length === 0) {
      setOpenRepairAfterVehicle(true);
      openAddVehicleModal();
      return;
    }
    resetRepairForm();
    setRepairModalOpen(true);
  }

  function closeRepairModal() {
    if (repairSaving) return;
    setRepairModalOpen(false);
    resetRepairForm();
  }

  function updateRepairLine(key: string, patch: Partial<RepairServiceLine>) {
    setRepairLines((rows) =>
      rows.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }

  function onRepairLineCatalogChange(key: string, serviceId: string) {
    if (serviceId === "__custom__") {
      updateRepairLine(key, { serviceId: "", name: "", cost: "" });
      return;
    }
    const svc = shopServices.find((s) => s.id === serviceId);
    if (!svc) {
      updateRepairLine(key, { serviceId: "", name: "", cost: "" });
      return;
    }
    updateRepairLine(key, {
      serviceId: svc.id,
      name: svc.name,
      cost: formatPrice(svc.price),
    });
  }

  function addRepairLine() {
    setRepairLines((rows) => [...rows, emptyRepairLine()]);
  }

  function removeRepairLine(key: string) {
    setRepairLines((rows) =>
      rows.length <= 1 ? rows : rows.filter((r) => r.key !== key),
    );
  }

  async function onAddRepair(e: FormEvent) {
    e.preventDefault();
    if (!repairVehicleId) {
      setError("Select a vehicle for this repair history.");
      return;
    }

    const lines = repairLines
      .map((row) => ({
        service_type: row.name.trim(),
        cost: Number(row.cost),
      }))
      .filter((row) => row.service_type.length > 0);

    if (lines.length === 0) {
      setError("Add at least one service (catalog or custom).");
      return;
    }
    for (const line of lines) {
      if (!Number.isFinite(line.cost) || line.cost < 0) {
        setError(`Enter a valid cost for “${line.service_type}” (0 or greater).`);
        return;
      }
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(repairDate)) {
      setError("Select a valid repair date.");
      return;
    }

    setRepairSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const description = repairDescription.trim();
      const recommendation = repairRecommendation.trim() || undefined;
      const created_at = dateInputToIso(repairDate);
      for (const line of lines) {
        await addRepairHistory(repairVehicleId, {
          service_type: line.service_type,
          description,
          cost: line.cost,
          recommendation,
          created_at,
        });
      }
      setRepairModalOpen(false);
      resetRepairForm();
      setSuccess(
        lines.length === 1
          ? "Repair history added."
          : `${lines.length} repair history entries added.`,
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add repair history");
    } finally {
      setRepairSaving(false);
    }
  }

  async function onConfirmDeleteCustomer() {
    if (!detail) return;
    setDeletingCustomer(true);
    setError(null);
    setSuccess(null);
    try {
      await deleteCustomer(customerId);
      setDeleteCustomerOpen(false);
      if (onDeleted) {
        onDeleted();
      } else {
        router.push("/dashboard/customer");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete customer");
      setDeletingCustomer(false);
    }
  }

  if (!customerId) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:h-full">
        <p className="text-sm text-red-700">Customer not found</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="surface-panel flex min-h-0 flex-1 flex-col overflow-hidden md:h-full">
        <div className="animate-pulse space-y-4 p-5">
          <div className="flex items-center gap-3">
            <div className="h-12 w-12 rounded-full bg-[var(--background)]" />
            <div className="space-y-2">
              <div className="h-4 w-40 rounded bg-[var(--background)]" />
              <div className="h-3 w-28 rounded bg-[var(--background)]" />
            </div>
          </div>
          <div className="h-9 w-full max-w-sm rounded-lg bg-[var(--background)]" />
          <div className="h-32 rounded-xl bg-[var(--background)]" />
        </div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="surface-panel flex min-h-0 flex-1 flex-col overflow-hidden p-5 md:h-full">
        <p className="text-sm text-red-700">{error ?? "Customer not found"}</p>
      </div>
    );
  }

  return (
    <div
      className={`flex min-h-0 flex-1 flex-col overflow-hidden touch-pan-y select-none md:h-full [&_input]:select-text [&_textarea]:select-text ${
        embedded ? "surface-panel" : "gap-4"
      }`}
      onPointerDown={onSwipePointerDown}
      onPointerUp={onSwipePointerUp}
      onPointerCancel={onSwipePointerCancel}
    >
      <div
        className={`shrink-0 ${
          embedded
            ? "border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/40 px-3 py-3 sm:px-4"
            : ""
        }`}
      >
        {embedded ? (
          <button
            type="button"
            onClick={() => onBack?.()}
            className="mb-1.5 text-xs font-medium text-[var(--accent)] lg:hidden"
          >
            ← list
          </button>
        ) : (
          <Link
            href="/dashboard/customer"
            className="text-sm text-[var(--muted)] hover:text-[var(--accent)]"
          >
            ← list
          </Link>
        )}

        <div className={`flex flex-wrap items-center justify-between gap-3 ${embedded ? "" : "mt-2"}`}>
          <div className="flex min-w-0 items-center gap-2.5">
            <span
              className={`inline-flex shrink-0 items-center justify-center rounded-full bg-[var(--accent)] font-semibold tracking-wide text-white shadow-sm ${
                embedded
                  ? "h-9 w-9 text-xs"
                  : "h-12 w-12 text-sm"
              }`}
              aria-hidden="true"
            >
              {customerInitials(detail.customer.name)}
            </span>
            <div className="min-w-0">
              <h1
                className={`truncate ${
                  embedded ? "page-title text-lg sm:text-xl" : "page-title"
                }`}
              >
                {detail.customer.name}
              </h1>
            </div>
          </div>

          <div
            className={`inline-flex rounded-full border border-[var(--line)] bg-white/80 shadow-sm backdrop-blur-sm ${
              embedded ? "p-0.5" : "p-1"
            }`}
            role="tablist"
            aria-label="Customer detail sections"
          >
            {DETAIL_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => selectTab(t.id)}
                className={`rounded-full font-medium transition ${
                  embedded
                    ? "px-2.5 py-1 text-xs"
                    : "px-3.5 py-1.5 text-sm"
                } ${
                  tab === t.id
                    ? "bg-[var(--accent)] text-white shadow-sm"
                    : "text-[var(--muted)] hover:text-[var(--foreground)]"
                }`}
              >
                {t.id === "repairs" ? (
                  <>
                    <span className="md:hidden">Repairs</span>
                    <span className="hidden md:inline">{t.label}</span>
                  </>
                ) : (
                  t.label
                )}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error &&
        !vehicleModal &&
        !repairModalOpen &&
        !deleteCustomerOpen &&
        !deleteVehicleTarget &&
        !deleteRepairTarget &&
        !deleteConversationTarget && (
        <p
          className={`shrink-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 ${
            embedded ? "mx-3 mt-3 sm:mx-4" : ""
          }`}
          role="alert"
        >
          {error}
        </p>
      )}
      {success &&
        !vehicleModal &&
        !repairModalOpen &&
        !deleteCustomerOpen &&
        !deleteVehicleTarget &&
        !deleteRepairTarget &&
        !deleteConversationTarget && (
        <p
          className={`shrink-0 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 ${
            embedded ? "mx-3 mt-3 sm:mx-4" : ""
          }`}
          role="status"
        >
          {success}
        </p>
      )}

      <div
        className={`min-h-0 flex-1 overscroll-contain ${
          tab === "profile" || tab === "repairs"
            ? "flex flex-col overflow-hidden"
            : "asa-scroll overflow-y-auto [scrollbar-gutter:stable]"
        } ${
          embedded
            ? tab === "profile"
              ? "gap-4 px-3 py-3 sm:px-4 sm:py-4"
              : tab === "repairs"
                ? ""
                : "space-y-4 px-3 py-3 sm:px-4 sm:py-4"
            : tab === "profile"
              ? "gap-6"
              : tab === "repairs"
                ? ""
                : "space-y-6"
        }`}
      >
      {tab === "profile" && (
        <div
          className={`asa-scroll flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain [scrollbar-gutter:stable] ${
            embedded ? "gap-4" : "gap-6"
          }`}
        >
          <section className={`shrink-0 ${embedded ? "space-y-3" : "surface-panel p-4 sm:p-5"}`}>
            <form
              onSubmit={onSaveCustomer}
              className="grid grid-cols-2 gap-3"
            >
              <Field
                label="Name"
                icon={<IconUser />}
                value={editName}
                onChange={setEditName}
                required
                disabled={!profileEditing}
              />
              <Field
                label="Phone"
                icon={<IconPhone />}
                type="tel"
                value={editPhone}
                onChange={(v) => setEditPhone(formatPhoneInput(v))}
                placeholder={PHONE_PLACEHOLDER}
                disabled={!profileEditing}
              />
              <Field
                label="Email"
                icon={<IconMail />}
                type="email"
                value={editEmail}
                onChange={setEditEmail}
                disabled={!profileEditing}
              />
              <Field
                label="Address"
                icon={<IconMapPin />}
                value={editAddress}
                onChange={setEditAddress}
                disabled={!profileEditing}
              />
              <div className="col-span-2 flex flex-wrap items-center gap-3">
                {profileEditing ? (
                  <>
                    <button
                      type="submit"
                      disabled={!profileDirty}
                      className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <IconSave />
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={cancelProfileEdit}
                      className="btn-ghost inline-flex items-center gap-1.5 px-4 py-2 text-sm"
                    >
                      <IconCancel />
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setSuccess(null);
                      setProfileEditing(true);
                    }}
                    className="btn-primary inline-flex items-center gap-1.5 px-4 py-2"
                  >
                    <IconPencil className="h-4 w-4" />
                    Edit
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setDeleteCustomerOpen(true);
                  }}
                  disabled={deletingCustomer}
                  className="inline-flex items-center gap-1.5 rounded-full border border-red-300 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <IconTrash />
                  Delete
                </button>
              </div>
            </form>
          </section>

          <section className="flex shrink-0 flex-col gap-2">
            <div className="flex shrink-0 items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-sm font-semibold">Vehicles</h2>
                <p className="mt-0.5 text-xs text-[var(--muted)]">
                  VIN, plate, and mileage for this customer
                </p>
              </div>
              <button
                type="button"
                onClick={openAddVehicleModal}
                aria-label="Add vehicle"
                className="btn-primary mr-3 inline-flex h-10 w-10 shrink-0 items-center justify-center p-0 sm:mr-4"
              >
                <IconCarPlus className="h-5 w-5" />
              </button>
            </div>

            <div className="rounded-xl border border-[var(--line)] bg-[var(--background)]/30 p-2.5">
              {detail.vehicles.length === 0 ? (
                <div className="flex min-h-[9.5rem] flex-col items-center justify-center px-3 text-center">
                  <span className="mb-2 inline-flex h-9 w-9 items-center justify-center rounded-full bg-white text-[var(--muted)] ring-1 ring-[var(--line)]">
                    <IconCar className="h-4 w-4" />
                  </span>
                  <p className="text-sm font-medium">No vehicles yet</p>
                  <p className="mt-0.5 text-xs text-[var(--muted)]">
                    Add a vehicle to log repair history and service visits.
                  </p>
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                  {detail.vehicles.map((v) => (
                    <article
                      key={v.id}
                      className="group rounded-xl border border-[var(--line)] bg-[var(--panel)] p-3 shadow-[var(--shadow-soft)] transition hover:border-[var(--accent)]/35"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 items-start gap-2.5">
                          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                            <IconCar className="h-3.5 w-3.5" />
                          </span>
                          <div className="min-w-0">
                            <h3 className="truncate text-sm font-semibold">
                              {vehicleLabel(v)}
                            </h3>
                            <p className="mt-0.5 font-mono text-[11px] text-[var(--muted)]">
                              {v.vin}
                            </p>
                          </div>
                        </div>
                      </div>
                      <dl className="mt-2 grid grid-cols-2 gap-1.5 text-xs">
                        <div className="rounded-lg bg-[var(--background)]/70 px-2 py-1.5">
                          <dt className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                            Plate
                          </dt>
                          <dd className="mt-0.5 font-medium">
                            {v.license_plate ?? "—"}
                          </dd>
                        </div>
                        <div className="rounded-lg bg-[var(--background)]/70 px-2 py-1.5">
                          <dt className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                            Mileage
                          </dt>
                          <dd className="mt-0.5 font-medium tabular-nums">
                            {v.mileage.toLocaleString()}
                          </dd>
                        </div>
                      </dl>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          onClick={() => openEditVehicleModal(v)}
                          disabled={deletingVehicleId === v.id}
                          className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] px-2.5 py-0.5 text-xs font-medium hover:border-[var(--accent)]/40 disabled:opacity-60"
                        >
                          <IconPencil />
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setDeleteVehicleTarget(v);
                          }}
                          disabled={deletingVehicleId === v.id}
                          className="inline-flex items-center gap-1.5 rounded-full border border-red-200 px-2.5 py-0.5 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                        >
                          <IconTrash className="h-3.5 w-3.5" />
                          {deletingVehicleId === v.id ? "Deleting…" : "Delete"}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {tab === "repairs" && (
        <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
          {/* Mobile: stacked cards so each repair fits the viewport width */}
          <div
            className={`asa-scroll min-h-0 flex-1 overflow-y-auto overscroll-contain pb-16 [scrollbar-gutter:auto] md:hidden ${
              embedded ? "px-3 py-3" : "px-0 py-1"
            }`}
          >
            {repairs.length === 0 ? (
              <div className="flex min-h-[12rem] flex-col items-center justify-center px-4 text-center text-sm text-[var(--muted)]">
                {detail.vehicles.length === 0 ? (
                  <span>
                    No repair history yet.{" "}
                    <button
                      type="button"
                      onClick={openAddRepairModal}
                      className="font-medium text-[var(--accent)] hover:underline"
                    >
                      Add a vehicle
                    </button>{" "}
                    to log the first service.
                  </span>
                ) : (
                  <span>
                    No repair history yet.{" "}
                    <button
                      type="button"
                      onClick={openAddRepairModal}
                      className="font-medium text-[var(--accent)] hover:underline"
                    >
                      Add the first entry
                    </button>
                    .
                  </span>
                )}
              </div>
            ) : (
              <ul className="space-y-2.5">
                {repairs.map((r) => (
                  <li
                    key={r.id}
                    className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-3 shadow-[var(--shadow-soft)]"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                          <p className="text-sm font-semibold leading-snug">
                            {r.service_type || "Service"}
                          </p>
                          <p className="text-xs tabular-nums text-[var(--muted)]">
                            {r.created_at
                              ? new Date(r.created_at).toLocaleDateString()
                              : "—"}
                          </p>
                        </div>
                        <p className="mt-0.5 truncate text-xs text-[var(--muted)]">
                          {r.vehicle_label}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <span className="text-sm font-semibold tabular-nums">
                          ${r.cost}
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setDeleteRepairTarget(r);
                          }}
                          disabled={deletingRepairId === r.id}
                          aria-label="Delete repair history"
                          title="Delete"
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-60"
                        >
                          <IconTrash className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                    {r.description ? (
                      <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-snug text-[var(--muted)]">
                        {r.description}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Desktop: wide table */}
          <div
            className={`table-scroll asa-scroll hidden min-h-0 flex-1 overflow-auto overscroll-contain pb-16 [scrollbar-gutter:auto] md:block ${
              embedded ? "rounded-none border-0 shadow-none" : ""
            }`}
          >
            <table>
              <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                <tr>
                  <th className="px-4 py-3 sm:px-5">Date</th>
                  <th className="px-4 py-3 sm:px-5">Vehicle</th>
                  <th className="px-4 py-3 sm:px-5">Service</th>
                  <th className="px-4 py-3 sm:px-5">Description</th>
                  <th className="px-4 py-3 sm:px-5">Cost</th>
                  <th className="w-14 px-4 py-3 sm:px-5">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {repairs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-[var(--muted)] sm:px-5">
                      {detail.vehicles.length === 0 ? (
                        <span>
                          No repair history yet.{" "}
                          <button
                            type="button"
                            onClick={openAddRepairModal}
                            className="font-medium text-[var(--accent)] hover:underline"
                          >
                            Add a vehicle
                          </button>{" "}
                          to log the first service.
                        </span>
                      ) : (
                        <span>
                          No repair history yet.{" "}
                          <button
                            type="button"
                            onClick={openAddRepairModal}
                            className="font-medium text-[var(--accent)] hover:underline"
                          >
                            Add the first entry
                          </button>
                          .
                        </span>
                      )}
                    </td>
                  </tr>
                ) : (
                  repairs.map((r) => (
                    <tr
                      key={r.id}
                      className="border-t border-[var(--line)] transition-colors hover:bg-[var(--background)]/60"
                    >
                      <td className="px-4 py-3 text-sm text-[var(--muted)] sm:px-5">
                        {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                      </td>
                      <td className="px-4 py-3 text-sm sm:px-5">{r.vehicle_label}</td>
                      <td className="px-4 py-3 text-sm font-medium sm:px-5">{r.service_type}</td>
                      <td className="px-4 py-3 text-sm text-[var(--muted)] sm:px-5">{r.description}</td>
                      <td className="px-4 py-3 text-sm tabular-nums sm:px-5">${r.cost}</td>
                      <td className="px-4 py-3 sm:px-5">
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setDeleteRepairTarget(r);
                          }}
                          disabled={deletingRepairId === r.id}
                          aria-label="Delete repair history"
                          title="Delete"
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-60"
                        >
                          <IconTrash className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            onClick={openAddRepairModal}
            aria-label="Add repair"
            className="btn-primary absolute bottom-3 right-3 z-10 inline-flex h-11 w-11 items-center justify-center p-0 shadow-md"
          >
            <IconWrenchPlus className="h-5 w-5" />
          </button>
        </section>
      )}

      {tab === "calls" && (
        <section className="space-y-5">
          {conversationsLoading && conversationTimeline.length === 0 ? (
            <div className="animate-pulse space-y-3 rounded-xl border border-[var(--line)] bg-[var(--background)]/50 p-5">
              <div className="h-4 w-40 rounded bg-[var(--background)]" />
              <div className="h-16 rounded-xl bg-[var(--background)]" />
              <div className="h-16 rounded-xl bg-[var(--background)]" />
            </div>
          ) : (
            <>
          {conversationTimeline.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {voiceCalls.length > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/80 px-3 py-1 text-xs font-medium text-[var(--muted)] shadow-sm">
                  <IconPhone className="h-3 w-3" />
                  {voiceCalls.length} call history
                </span>
              )}
              {smsConversations.length > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/80 px-3 py-1 text-xs font-medium text-[var(--muted)] shadow-sm">
                  <IconMessage className="h-3 w-3" />
                  {smsConversations.length} SMS
                </span>
              )}
              {otherMessageCount > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/80 px-3 py-1 text-xs font-medium text-[var(--muted)] shadow-sm">
                  <IconMessage className="h-3 w-3" />
                  {otherMessageCount} message
                  {otherMessageCount === 1 ? "" : "s"}
                </span>
              )}
            </div>
          )}

          {conversationTimeline.length === 0 ? (
            <div className="flex flex-col items-center rounded-xl border border-dashed border-[var(--line)] bg-[var(--background)]/50 px-6 py-12 text-center">
              <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-white text-[var(--muted)] shadow-sm ring-1 ring-[var(--line)]">
                <IconMessage className="h-5 w-5" />
              </span>
              <p className="text-sm font-medium">No calls yet</p>
              <p className="mt-1 max-w-xs text-xs text-[var(--muted)]">
                Call history and messages will appear here once this customer starts contacting the shop.
              </p>
              <Link
                href="/dashboard/calls?tab=calls"
                className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-[var(--accent)] hover:underline"
              >
                Open Calls
                <IconChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          ) : (
            <ol className="relative space-y-3 before:absolute before:bottom-4 before:left-[1.125rem] before:top-4 before:w-px before:bg-[var(--line)]">
              {conversationTimeline.map((item) => {
                if (item.kind === "call") {
                  const c = item.call;
                  const when = formatConversationWhen(c.started_at || c.created_at);
                  const duration = formatCallDuration(c);
                  return (
                    <li key={item.id} className="relative flex items-center gap-3">
                      <span className="relative z-10 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white shadow-sm ring-4 ring-[var(--panel)]">
                        <IconPhone className="h-3.5 w-3.5" />
                      </span>
                      <div className="group relative min-w-0 flex-1 rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)] transition hover:border-[var(--accent)]/40 hover:shadow-md">
                        <Link
                          href={`/dashboard/calls?tab=calls&id=${encodeURIComponent(c.id)}`}
                          className="flex min-h-9 items-center px-4 py-2.5 pr-14"
                        >
                          <p className="text-sm font-medium tabular-nums leading-none">
                            {when}
                            {duration ? (
                              <span className="font-normal text-[var(--muted)]">
                                {" "}
                                · {duration}
                              </span>
                            ) : null}
                          </p>
                        </Link>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setError(null);
                            setDeleteConversationTarget({ kind: "call", call: c });
                          }}
                          disabled={deletingConversation}
                          aria-label="Delete call history"
                          title="Delete"
                          className="absolute right-3 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-60"
                        >
                          <IconTrash className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </li>
                  );
                }

                if (item.kind === "sms") {
                  const s = item.sms;
                  const when = formatConversationWhen(
                    s.last_message_at || s.created_at,
                  );
                  const preview =
                    s.reply_preview ||
                    s.owner_summary ||
                    s.last_intent ||
                    "SMS conversation";
                  return (
                    <li key={item.id} className="relative flex items-start gap-3">
                      <span className="relative z-10 mt-2.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-white shadow-sm ring-4 ring-[var(--panel)]">
                        <IconMessage className="h-3.5 w-3.5" />
                      </span>
                      <div className="group relative min-w-0 flex-1 rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)] transition hover:border-[var(--accent)]/40 hover:shadow-md">
                        <Link
                          href={`/dashboard/calls?tab=sms&id=${encodeURIComponent(s.id)}`}
                          className="block cursor-pointer px-4 py-2.5 pr-14"
                        >
                          <p className="flex min-h-9 items-center text-sm font-medium tabular-nums leading-none">
                            {when}
                            <span className="font-normal text-[var(--muted)]">
                              &nbsp;· SMS
                            </span>
                          </p>
                          <p className="mt-1 line-clamp-2 text-xs text-[var(--muted)]">
                            {preview}
                          </p>
                        </Link>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            setError(null);
                            setDeleteConversationTarget({ kind: "sms", sms: s });
                          }}
                          disabled={deletingConversation}
                          aria-label="Delete SMS conversation"
                          title="Delete"
                          className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-60"
                        >
                          <IconTrash className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </li>
                  );
                }

                const m = item.comm;
                const ChannelIcon =
                  m.channel === "email"
                    ? IconMail
                    : m.channel === "phone"
                      ? IconPhone
                      : IconMessage;
                const when = formatConversationWhen(m.created_at);
                return (
                  <li key={item.id} className="relative flex items-start gap-3">
                    <span className="relative z-10 mt-2.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--line)] bg-[var(--background)] text-[var(--muted)] shadow-sm ring-4 ring-[var(--panel)]">
                      <ChannelIcon className="h-3.5 w-3.5" />
                    </span>
                    <article className="flex min-w-0 flex-1 items-start gap-2 rounded-xl border border-[var(--line)] bg-[var(--panel)] px-4 py-2.5 shadow-[var(--shadow-soft)]">
                      <div className="min-w-0 flex-1">
                        <div className="flex min-h-9 flex-wrap items-center gap-x-2 gap-y-1">
                          <p className="text-sm font-medium tabular-nums leading-none">
                            {when}
                          </p>
                          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                            {channelLabel(m.channel)}
                          </span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                              m.direction === "incoming"
                                ? "bg-sky-50 text-sky-800"
                                : "bg-[var(--accent-soft)] text-[var(--accent)]"
                            }`}
                          >
                            {m.direction === "incoming" ? "Inbound" : "Outbound"}
                          </span>
                        </div>
                        <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed">
                          {m.message}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setError(null);
                          setDeleteConversationTarget({ kind: "comm", comm: m });
                        }}
                        disabled={deletingConversation}
                        aria-label="Delete message"
                        title="Delete"
                        className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        <IconTrash className="h-3.5 w-3.5" />
                      </button>
                    </article>
                  </li>
                );
              })}
            </ol>
          )}
            </>
          )}
        </section>
      )}
      </div>

      {repairModalOpen &&
        createPortal(
          (() => {
            const selectedVehicle =
              detail.vehicles.find((v) => v.id === repairVehicleId) ??
              detail.vehicles[0] ??
              null;
            const filledLines = repairLines.filter((r) => r.name.trim());
            const repairTotal = filledLines.reduce((sum, r) => {
              const n = Number(r.cost);
              return sum + (Number.isFinite(n) ? n : 0);
            }, 0);
            const servicePreview =
              filledLines
                .slice(0, 2)
                .map((r) => r.name.trim())
                .join(", ") || "No services selected yet";

            return (
              <div
                className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
                role="dialog"
                aria-modal="true"
                aria-labelledby="add-repair-title"
                onClick={() => {
                  if (!repairSaving) closeRepairModal();
                }}
              >
                <div
                  className="flex max-h-[min(82dvh,36rem)] w-full max-w-[28rem] flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-4 pb-3.5 pt-4">
                    <div
                      className="pointer-events-none absolute right-0 top-0 h-28 w-28 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                      aria-hidden="true"
                    />
                    <div className="relative flex min-w-0 items-center gap-2.5">
                      <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]">
                        <IconWrench className="h-3.5 w-3.5" />
                      </span>
                      <h2
                        id="add-repair-title"
                        className="text-base font-semibold tracking-tight text-[var(--ink)]"
                      >
                        Add repair history
                      </h2>
                    </div>
                  </div>

                  {detail.vehicles.length === 0 ? (
                    <>
                      <div className="space-y-3 px-4 py-4">
                        <div className="rounded-xl border border-dashed border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-4 py-6 text-center">
                          <span className="mx-auto inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-900 text-white">
                            <IconCar className="h-4 w-4" />
                          </span>
                          <p className="mt-2.5 text-sm font-semibold text-slate-900">
                            Add a vehicle first
                          </p>
                          <p className="mt-1 text-xs text-[var(--muted)]">
                            Repair history is logged per vehicle.
                          </p>
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-row justify-end gap-2 border-t border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-4 py-3">
                        <button
                          type="button"
                          onClick={closeRepairModal}
                          className="btn-ghost inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm"
                        >
                          <IconCancel />
                          Cancel
                        </button>
                      </div>
                    </>
                  ) : (
                    <form
                      onSubmit={onAddRepair}
                      className="flex min-h-0 flex-1 flex-col"
                    >
                      <div className="asa-scroll min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-4 py-4">
                        <div className="flex items-start gap-2.5 rounded-xl border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3 py-2.5">
                          <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white">
                            <IconCar className="h-3.5 w-3.5" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-semibold text-slate-900">
                              {selectedVehicle
                                ? vehicleLabel(selectedVehicle)
                                : "Select a vehicle"}
                            </p>
                            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[var(--muted)]">
                              {selectedVehicle?.license_plate ? (
                                <span>Plate {selectedVehicle.license_plate}</span>
                              ) : (
                                <span>No plate on file</span>
                              )}
                              {repairDate ? (
                                <span>
                                  {new Date(
                                    dateInputToIso(repairDate),
                                  ).toLocaleDateString()}
                                </span>
                              ) : null}
                              <span>
                                {filledLines.length} service
                                {filledLines.length === 1 ? "" : "s"}
                              </span>
                              <span className="tabular-nums font-medium text-slate-800">
                                ${formatPrice(repairTotal)}
                              </span>
                            </div>
                            <p className="mt-1.5 line-clamp-1 text-xs text-[var(--muted)]">
                              {servicePreview}
                              {filledLines.length > 2
                                ? ` +${filledLines.length - 2} more`
                                : ""}
                            </p>
                          </div>
                        </div>

                        {error && (
                          <p
                            className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                            role="alert"
                          >
                            {error}
                          </p>
                        )}

                        <div className="space-y-3">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                            Vehicle
                          </p>
                          <label className="block space-y-1.5">
                            <span className="text-sm font-medium">Which vehicle was serviced?</span>
                            <select
                              value={repairVehicleId}
                              required
                              onChange={(e) => setRepairVehicleId(e.target.value)}
                              className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                            >
                              {detail.vehicles.map((v) => (
                                <option key={v.id} value={v.id}>
                                  {vehicleLabel(v)}
                                  {v.license_plate ? ` · ${v.license_plate}` : ""}
                                </option>
                              ))}
                            </select>
                          </label>
                          <label className="block space-y-1.5">
                            <span className="text-sm font-medium">Repair date</span>
                            <input
                              type="date"
                              value={repairDate}
                              required
                              max={todayDateInputValue()}
                              onChange={(e) => setRepairDate(e.target.value)}
                              className="w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                            />
                          </label>
                        </div>

                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                              Services
                            </p>
                            <button
                              type="button"
                              onClick={addRepairLine}
                              className="inline-flex items-center gap-1 text-sm font-medium text-[var(--accent)] transition hover:opacity-80"
                            >
                              <IconPlus className="h-3.5 w-3.5" />
                              Add line
                            </button>
                          </div>
                          <p className="text-xs leading-relaxed text-[var(--muted)]">
                            Tap catalog chips below, or choose Custom and type a name. Costs stay
                            editable.
                          </p>

                          {shopServices.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                              {shopServices.map((svc) => {
                                const selected = repairLines.some(
                                  (r) =>
                                    r.serviceId === svc.id || r.name.trim() === svc.name,
                                );
                                return (
                                  <button
                                    key={svc.id}
                                    type="button"
                                    onClick={() => {
                                      if (selected) {
                                        setRepairLines((rows) => {
                                          const next = rows.filter(
                                            (r) =>
                                              r.serviceId !== svc.id &&
                                              r.name.trim() !== svc.name,
                                          );
                                          return next.length > 0
                                            ? next
                                            : [emptyRepairLine()];
                                        });
                                        return;
                                      }
                                      setRepairLines((rows) => {
                                        const blankIdx = rows.findIndex(
                                          (r) => !r.name.trim() && !r.serviceId,
                                        );
                                        const line = emptyRepairLine({
                                          serviceId: svc.id,
                                          name: svc.name,
                                          cost: formatPrice(svc.price),
                                        });
                                        if (blankIdx >= 0) {
                                          const next = [...rows];
                                          next[blankIdx] = line;
                                          return next;
                                        }
                                        return [...rows, line];
                                      });
                                    }}
                                    className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                                      selected
                                        ? "border-[var(--accent)] bg-[var(--accent)] text-white shadow-sm shadow-[var(--accent-glow)]"
                                        : "border-[var(--line)] bg-white text-[var(--muted)] hover:border-[var(--accent)]/50 hover:text-[var(--foreground)]"
                                    }`}
                                  >
                                    {svc.name}
                                  </button>
                                );
                              })}
                            </div>
                          )}

                          <div className="space-y-3">
                            {repairLines.map((row, index) => (
                              <div
                                key={row.key}
                                className="rounded-xl border border-[var(--line)] bg-white p-3.5 shadow-[var(--shadow-soft)]"
                              >
                                <div className="mb-2.5 flex items-center justify-between gap-2">
                                  <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
                                    Line {index + 1}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => removeRepairLine(row.key)}
                                    disabled={repairLines.length <= 1}
                                    className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line)] text-[var(--muted)] transition hover:border-red-300 hover:bg-red-50 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-40"
                                    aria-label={`Remove service ${index + 1}`}
                                  >
                                    <IconTrash className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                                <div className="grid grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_6rem] gap-2.5">
                                  <label className="block space-y-1">
                                    <span className="text-xs text-[var(--muted)]">Catalog</span>
                                    <select
                                      value={
                                        row.serviceId || (row.name ? "__custom__" : "")
                                      }
                                      onChange={(e) =>
                                        onRepairLineCatalogChange(row.key, e.target.value)
                                      }
                                      className="w-full rounded-lg border border-[var(--line)] bg-[var(--background)]/40 px-2.5 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                                    >
                                      <option value="" disabled>
                                        Select…
                                      </option>
                                      {shopServices.map((s) => (
                                        <option key={s.id} value={s.id}>
                                          {s.name}
                                          {` · $${formatPrice(s.price)}`}
                                        </option>
                                      ))}
                                      <option value="__custom__">Custom (type name)</option>
                                    </select>
                                  </label>
                                  <label className="block space-y-1">
                                    <span className="text-xs text-[var(--muted)]">
                                      Service name
                                    </span>
                                    <input
                                      type="text"
                                      value={row.name}
                                      required={
                                        index === 0 ||
                                        Boolean(row.serviceId) ||
                                        Boolean(row.cost.trim()) ||
                                        Boolean(row.name.trim())
                                      }
                                      onChange={(e) => {
                                        const name = e.target.value;
                                        const matched = shopServices.find(
                                          (s) => s.name === name,
                                        );
                                        updateRepairLine(row.key, {
                                          name,
                                          serviceId: matched?.id ?? "",
                                        });
                                      }}
                                      placeholder="e.g. Oil Change"
                                      maxLength={100}
                                      className="w-full rounded-lg border border-[var(--line)] bg-[var(--background)]/40 px-2.5 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                                    />
                                  </label>
                                  <label className="block space-y-1">
                                    <span className="text-xs text-[var(--muted)]">Cost</span>
                                    <div className="relative">
                                      <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-[var(--muted)]">
                                        $
                                      </span>
                                      <input
                                        type="number"
                                        min={0}
                                        step="0.01"
                                        value={row.cost}
                                        required={Boolean(row.name.trim())}
                                        onChange={(e) =>
                                          updateRepairLine(row.key, {
                                            cost: e.target.value,
                                          })
                                        }
                                        placeholder="0.00"
                                        className="w-full rounded-lg border border-[var(--line)] bg-[var(--background)]/40 py-2 pl-6 pr-2.5 text-sm tabular-nums outline-none ring-[var(--accent)] focus:ring-2"
                                      />
                                    </div>
                                  </label>
                                </div>
                              </div>
                            ))}
                          </div>

                          {shopServices.length === 0 && (
                            <p className="rounded-xl border border-dashed border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-3 text-xs leading-relaxed text-[var(--muted)]">
                              No catalog services yet — type a custom name, or add services in{" "}
                              <Link
                                href="/dashboard/settings?tab=shop"
                                className="font-medium text-[var(--accent)] hover:underline"
                              >
                                Service Catalog
                              </Link>
                              .
                            </p>
                          )}
                        </div>

                        <div className="space-y-3">
                          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                            Notes
                          </p>
                          <label className="block space-y-1.5">
                            <span className="text-sm font-medium">Description</span>
                            <textarea
                              value={repairDescription}
                              onChange={(e) => setRepairDescription(e.target.value)}
                              rows={2}
                              placeholder="What was done (applies to all services above)"
                              className="w-full resize-y rounded-xl border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                            />
                          </label>
                          <label className="block space-y-1.5">
                            <span className="text-sm font-medium">
                              Follow-up recommendation{" "}
                              <span className="font-normal text-[var(--muted)]">(optional)</span>
                            </span>
                            <textarea
                              value={repairRecommendation}
                              onChange={(e) => setRepairRecommendation(e.target.value)}
                              rows={2}
                              placeholder="e.g. Replace pads within 6 months — used in Marketing"
                              className="w-full resize-y rounded-xl border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                            />
                          </label>
                        </div>
                      </div>

                      <div className="flex shrink-0 flex-row items-center justify-between gap-2 border-t border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-4 py-3">
                        <p className="text-left text-xs text-[var(--muted)]">
                          {filledLines.length > 0 ? (
                            <>
                              <span className="font-medium text-slate-800">
                                {filledLines.length} service
                                {filledLines.length === 1 ? "" : "s"}
                              </span>
                              <span className="mx-1.5 text-[var(--line)]">·</span>
                              <span className="tabular-nums font-semibold text-slate-900">
                                ${formatPrice(repairTotal)}
                              </span>
                            </>
                          ) : (
                            "Select at least one service to save"
                          )}
                        </p>
                        <div className="flex flex-row justify-end gap-2">
                          <button
                            type="button"
                            onClick={closeRepairModal}
                            disabled={repairSaving}
                            className="btn-ghost inline-flex items-center justify-center gap-1.5 px-3.5 py-1.5 text-sm disabled:opacity-60"
                          >
                            <IconCancel />
                            Cancel
                          </button>
                          <button
                            type="submit"
                            disabled={
                              repairSaving ||
                              !repairVehicleId ||
                              !repairLines.some((r) => r.name.trim())
                            }
                            className="btn-primary inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
                          >
                            {!repairSaving && <IconSave />}
                            {repairSaving ? "Saving…" : "Save"}
                          </button>
                        </div>
                      </div>
                    </form>
                  )}
                </div>
              </div>
            );
          })(),
          document.body,
        )}

      {deleteRepairTarget &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-repair-title"
            onClick={() => {
              if (!deletingRepairId) setDeleteRepairTarget(null);
            }}
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
                    id="delete-repair-title"
                    className="text-lg font-semibold tracking-tight text-slate-900"
                  >
                    Delete repair history?
                  </h2>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                <div className="flex items-start gap-3 rounded-xl border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-3">
                  <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
                    <IconWrench className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      {deleteRepairTarget.service_type}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[var(--muted)]">
                      <span>{deleteRepairTarget.vehicle_label}</span>
                      {deleteRepairTarget.created_at ? (
                        <span>
                          {new Date(deleteRepairTarget.created_at).toLocaleDateString()}
                        </span>
                      ) : null}
                      <span className="tabular-nums">${deleteRepairTarget.cost}</span>
                    </div>
                    {deleteRepairTarget.description ? (
                      <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-[var(--muted)]">
                        {deleteRepairTarget.description}
                      </p>
                    ) : null}
                  </div>
                </div>

                <p className="text-sm leading-relaxed text-[var(--muted)]">
                  This cannot be undone. The service record will be permanently removed
                  from this customer&apos;s history.
                </p>

                {error && (
                  <p
                    className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                    role="alert"
                  >
                    {error}
                  </p>
                )}

                <div className="flex flex-row justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setDeleteRepairTarget(null)}
                    disabled={!!deletingRepairId}
                    className="btn-ghost px-4 py-2 text-sm disabled:opacity-60"
                  >
                    No
                  </button>
                  <button
                    type="button"
                    onClick={() => void onConfirmDeleteRepair()}
                    disabled={!!deletingRepairId}
                    className="inline-flex items-center justify-center rounded-full bg-red-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm shadow-red-600/20 transition hover:bg-red-700 disabled:opacity-60"
                  >
                    {deletingRepairId ? "Deleting…" : "Yes"}
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {deleteConversationTarget &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-conversation-title"
            onClick={() => {
              if (!deletingConversation) setDeleteConversationTarget(null);
            }}
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
                    id="delete-conversation-title"
                    className="text-lg font-semibold tracking-tight text-slate-900"
                  >
                    {deleteConversationTarget.kind === "call"
                      ? "Delete call history?"
                      : deleteConversationTarget.kind === "sms"
                        ? "Delete SMS conversation?"
                        : "Delete message?"}
                  </h2>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                <p className="text-sm leading-relaxed text-[var(--muted)]">
                  This cannot be undone. The{" "}
                  {deleteConversationTarget.kind === "call"
                    ? "call history"
                    : deleteConversationTarget.kind === "sms"
                      ? "SMS conversation"
                      : "message"}{" "}
                  will be permanently removed from this customer&apos;s history.
                </p>

                {error && (
                  <p
                    className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                    role="alert"
                  >
                    {error}
                  </p>
                )}

                <div className="flex flex-row justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setDeleteConversationTarget(null)}
                    disabled={deletingConversation}
                    className="btn-ghost px-4 py-2 text-sm disabled:opacity-60"
                  >
                    No
                  </button>
                  <button
                    type="button"
                    onClick={() => void onConfirmDeleteConversation()}
                    disabled={deletingConversation}
                    className="inline-flex items-center justify-center rounded-full bg-red-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm shadow-red-600/20 transition hover:bg-red-700 disabled:opacity-60"
                  >
                    {deletingConversation ? "Deleting…" : "Yes"}
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {deleteVehicleTarget &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-vehicle-title"
            onClick={() => {
              if (!deletingVehicleId) setDeleteVehicleTarget(null);
            }}
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
                    id="delete-vehicle-title"
                    className="text-lg font-semibold tracking-tight text-slate-900"
                  >
                    Delete this vehicle?
                  </h2>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                <div className="flex items-start gap-3 rounded-xl border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-3">
                  <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
                    <IconCar className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      {vehicleLabel(deleteVehicleTarget)}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[var(--muted)]">
                      {deleteVehicleTarget.license_plate ? (
                        <span>Plate {deleteVehicleTarget.license_plate}</span>
                      ) : null}
                      {deleteVehicleTarget.vin ? (
                        <span className="font-mono tracking-wide">
                          VIN {deleteVehicleTarget.vin}
                        </span>
                      ) : null}
                      {!deleteVehicleTarget.license_plate && !deleteVehicleTarget.vin ? (
                        <span>No plate or VIN on file</span>
                      ) : null}
                    </div>
                  </div>
                </div>

                <p className="text-sm leading-relaxed text-[var(--muted)]">
                  This cannot be undone. Repair history for this vehicle will also be
                  removed from your shop.
                </p>

                {error && (
                  <p
                    className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                    role="alert"
                  >
                    {error}
                  </p>
                )}

                <div className="flex flex-row justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setDeleteVehicleTarget(null)}
                    disabled={!!deletingVehicleId}
                    className="btn-ghost px-4 py-2 text-sm disabled:opacity-60"
                  >
                    No
                  </button>
                  <button
                    type="button"
                    onClick={() => void onConfirmDeleteVehicle()}
                    disabled={!!deletingVehicleId}
                    className="inline-flex items-center justify-center rounded-full bg-red-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm shadow-red-600/20 transition hover:bg-red-700 disabled:opacity-60"
                  >
                    {deletingVehicleId ? "Deleting…" : "Yes"}
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {deleteCustomerOpen &&
        detail &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-customer-title"
            onClick={() => {
              if (!deletingCustomer) setDeleteCustomerOpen(false);
            }}
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
                    id="delete-customer-title"
                    className="text-lg font-semibold tracking-tight text-slate-900"
                  >
                    Delete this customer?
                  </h2>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                <p className="text-sm leading-relaxed text-[var(--muted)]">
                  This cannot be undone. All linked records for this person will be
                  removed from your shop.
                </p>

                {error && (
                  <p
                    className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                    role="alert"
                  >
                    {error}
                  </p>
                )}

                <div className="flex flex-row justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setDeleteCustomerOpen(false)}
                    disabled={deletingCustomer}
                    className="btn-ghost px-4 py-2 text-sm disabled:opacity-60"
                  >
                    No
                  </button>
                  <button
                    type="button"
                    onClick={() => void onConfirmDeleteCustomer()}
                    disabled={deletingCustomer}
                    className="inline-flex items-center justify-center rounded-full bg-red-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm shadow-red-600/20 transition hover:bg-red-700 disabled:opacity-60"
                  >
                    {deletingCustomer ? "Deleting…" : "Yes"}
                  </button>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {vehicleModal &&
        createPortal(
          <div
            className="fixed inset-0 z-[100]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="vehicle-modal-title"
            onPointerDown={(e) => e.stopPropagation()}
            onPointerUp={(e) => e.stopPropagation()}
            onPointerCancel={(e) => e.stopPropagation()}
          >
            {/* Dedicated full-screen layer so outside clicks always close
                (flex gutters alone can miss hit-testing on some browsers). */}
            <button
              type="button"
              tabIndex={-1}
              aria-label="Close vehicle dialog"
              className="absolute inset-0 cursor-default bg-slate-950/55 backdrop-blur-[2px]"
              disabled={vehicleSaving || Boolean(deletingVehicleId)}
              onPointerDown={(e) => {
                // pointerdown closes more reliably than click on touch (slight
                // movement often suppresses the click event).
                if (e.button !== 0) return;
                if (vehicleSaving || deletingVehicleId) return;
                e.preventDefault();
                closeVehicleModal();
              }}
            />
            <div className="pointer-events-none relative flex h-full items-center justify-center p-4">
              <div className="pointer-events-auto flex max-h-[min(90dvh,42rem)] w-full max-w-[28rem] flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]">
              <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 pb-5 pt-6">
                <div
                  className="pointer-events-none absolute right-0 top-0 h-40 w-40 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                  aria-hidden="true"
                />
                <div className="relative flex min-w-0 items-center gap-3">
                  <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]">
                    {vehicleModal === "edit" ? (
                      <IconPencil className="h-4 w-4" />
                    ) : (
                      <IconCar className="h-4 w-4" />
                    )}
                  </span>
                  <h2
                    id="vehicle-modal-title"
                    className="text-lg font-semibold tracking-tight text-[var(--ink)]"
                  >
                    {vehicleModal === "edit" ? "Edit vehicle" : "Add vehicle"}
                  </h2>
                </div>
              </div>

              <form
                onSubmit={onSaveVehicle}
                className="flex min-h-0 flex-1 flex-col"
              >
                <div className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-5">
                  <div className="flex items-start gap-3 rounded-xl border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-3">
                    <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
                      <IconCar className="h-4 w-4" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {[year, make, model].map((v) => v.trim()).filter(Boolean).join(" ") ||
                          (vehicleModal === "edit" ? "Vehicle" : "New vehicle")}
                      </p>
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[var(--muted)]">
                        {plate.trim() ? <span>Plate {plate.trim()}</span> : null}
                        {vin.trim() ? (
                          <span className="font-mono tracking-wide">
                            VIN {vin.trim().toUpperCase()}
                          </span>
                        ) : (
                          <span>VIN optional — temp VIN if blank</span>
                        )}
                        {(() => {
                          const n = Number(mileage.replace(/,/g, "").trim());
                          return Number.isFinite(n) && n > 0 ? (
                            <span className="tabular-nums">
                              {n.toLocaleString()} mi
                            </span>
                          ) : null;
                        })()}
                      </div>
                      {(vinLooking || vinStatus) && (
                        <p className="mt-1.5 text-xs text-[var(--muted)]">
                          {vinLooking ? "Looking up VIN…" : vinStatus}
                        </p>
                      )}
                    </div>
                  </div>

                  {error && (
                    <p
                      className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                      role="alert"
                    >
                      {error}
                    </p>
                  )}

                  <div className="space-y-3">
                    <VinInput
                      value={vin}
                      onChange={setVin}
                      status={vinStatus}
                      looking={vinLooking}
                      required={vehicleModal === "edit"}
                    />
                    <Field
                      label="License plate"
                      value={plate}
                      onChange={setPlate}
                      placeholder="Optional"
                    />
                  </div>

                  <div className="space-y-3">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--muted)]">
                      Specs
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <Field
                        label="Year"
                        value={year}
                        onChange={setYear}
                        required={vehicleModal === "edit"}
                        placeholder={vehicleModal === "add" ? "e.g. 2018" : undefined}
                      />
                      <Field
                        label="Make"
                        value={make}
                        onChange={setMake}
                        required={vehicleModal === "edit"}
                        placeholder={vehicleModal === "add" ? "e.g. Toyota" : undefined}
                      />
                      <Field
                        label="Model"
                        value={model}
                        onChange={setModel}
                        required={vehicleModal === "edit"}
                        placeholder={vehicleModal === "add" ? "e.g. Camry" : undefined}
                      />
                      <Field
                        label="Mileage"
                        value={mileage}
                        onChange={setMileage}
                        required={vehicleModal === "edit"}
                        placeholder={vehicleModal === "add" ? "Optional" : undefined}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex shrink-0 flex-row justify-end gap-2 border-t border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-5 py-4">
                  <button
                    type="button"
                    onClick={closeVehicleModal}
                    disabled={vehicleSaving || Boolean(deletingVehicleId)}
                    className="btn-ghost inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm disabled:opacity-60"
                  >
                    <IconCancel />
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={
                      vehicleSaving ||
                      Boolean(deletingVehicleId) ||
                      (vehicleModal === "edit" && !vehicleDirty) ||
                      (vehicleModal === "add" &&
                        ![vin, plate, year, make, model, mileage].some(
                          (v) => v.trim().length > 0,
                        ))
                    }
                    className="btn-primary inline-flex items-center justify-center gap-1.5 px-5 py-2.5 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {!vehicleSaving && <IconSave />}
                    {vehicleSaving
                      ? "Saving…"
                      : openRepairAfterVehicle
                        ? "Save & continue"
                        : "Save"}
                  </button>
                </div>
              </form>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}

function Field({
  label,
  icon,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
  disabled,
}: {
  label: string;
  icon?: ReactNode;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="inline-flex items-center gap-1.5 text-sm font-medium">
        {icon ? <span className="text-[var(--muted)]">{icon}</span> : null}
        {label}
      </span>
      <input
        type={type}
        value={value}
        required={required && !disabled}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => {
          if (disabled) return;
          onChange(e.target.value);
        }}
        className={`w-full rounded-md border border-[var(--line)] px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2 disabled:cursor-not-allowed disabled:bg-[var(--background)] disabled:text-[var(--ink)] disabled:opacity-100 ${
          disabled ? "focus:ring-0" : "bg-white"
        }`}
      />
    </label>
  );
}
