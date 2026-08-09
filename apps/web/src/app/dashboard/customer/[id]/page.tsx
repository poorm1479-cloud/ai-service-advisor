"use client";

import Link from "next/link";
import {
  FormEvent,
  ReactNode,
  Suspense,
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
import { VinInput } from "@/components/VinInput";
import { formatPhoneInput, PHONE_PLACEHOLDER } from "@/lib/phone";
import { deleteVoiceCall, listVoiceCalls, VoiceCall } from "@/lib/calls";
import {
  formatPrice,
  listShopServices,
  ShopService,
} from "@/lib/shopSetup";
import { vinAssist } from "@/lib/walkin";

const DETAIL_TABS = [
  { id: "profile", label: "Profile" },
  { id: "repairs", label: "Repair history" },
  { id: "conversations", label: "Conversations" },
] as const;

type DetailTab = (typeof DETAIL_TABS)[number]["id"];

function parseDetailTab(value: string | null): DetailTab {
  if (value === "repairs" || value === "conversations" || value === "profile") {
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

  const [editName, setEditName] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editAddress, setEditAddress] = useState("");

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
  /** After adding a vehicle from the Repair tab, open the repair modal. */
  const [openRepairAfterVehicle, setOpenRepairAfterVehicle] = useState(false);
  const [vinStatus, setVinStatus] = useState<string | null>(null);
  const [vinLooking, setVinLooking] = useState(false);
  const vinAssistSeq = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
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

      // Secondary tabs — do not block first paint
      const callsAll = await listVoiceCalls().catch(() => [] as VoiceCall[]);
      setVoiceCalls(callsAll.filter((c) => c.customer_id === customerId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load customer");
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    if (!authLoading && session && customerId) {
      void load();
    }
  }, [authLoading, session, customerId, load]);

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
    for (const comm of detail?.communications ?? []) {
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
  }, [voiceCalls, detail?.communications]);

  useEffect(() => {
    if (profileDirty) setSuccess(null);
  }, [profileDirty]);

  async function onSaveCustomer(e: FormEvent) {
    e.preventDefault();
    if (!profileDirty) return;
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
        setSuccess("Call deleted.");
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

    setRepairSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const description = repairDescription.trim();
      for (const line of lines) {
        await addRepairHistory(repairVehicleId, {
          service_type: line.service_type,
          description,
          cost: line.cost,
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
      className={`flex min-h-0 flex-1 flex-col overflow-hidden md:h-full ${
        embedded ? "surface-panel" : "gap-4"
      }`}
    >
      <div
        className={`shrink-0 ${
          embedded
            ? "border-b border-[var(--line)] bg-gradient-to-br from-white via-white to-[var(--accent-soft)]/40 px-4 py-4 sm:px-5"
            : ""
        }`}
      >
        {embedded ? (
          <button
            type="button"
            onClick={() => onBack?.()}
            className="mb-2 text-xs font-medium text-[var(--accent)] lg:hidden"
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

        <div className={`flex flex-wrap items-center justify-between gap-4 ${embedded ? "" : "mt-2"}`}>
          <div className="flex min-w-0 items-center gap-3">
            <span
              className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[var(--accent)] text-sm font-semibold tracking-wide text-white shadow-sm"
              aria-hidden="true"
            >
              {customerInitials(detail.customer.name)}
            </span>
            <div className="min-w-0">
              <h1 className="page-title truncate">{detail.customer.name}</h1>
            </div>
          </div>

          <div
            className="inline-flex rounded-full border border-[var(--line)] bg-white/80 p-1 shadow-sm backdrop-blur-sm"
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
                className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
                  tab === t.id
                    ? "bg-[var(--accent)] text-white shadow-sm"
                    : "text-[var(--muted)] hover:text-[var(--foreground)]"
                }`}
              >
                {t.label}
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
            embedded ? "mx-4 mt-4 sm:mx-5" : ""
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
            embedded ? "mx-4 mt-4 sm:mx-5" : ""
          }`}
          role="status"
        >
          {success}
        </p>
      )}

      <div
        className={`asa-scroll min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain [scrollbar-gutter:auto] ${
          embedded ? "px-4 py-4 sm:px-5 sm:py-5" : ""
        }`}
      >
      {tab === "profile" && (
        <div className="space-y-6">
          <section className={embedded ? "space-y-3" : "surface-panel p-4 sm:p-5"}>
            <form
              onSubmit={onSaveCustomer}
              className="grid gap-3 sm:grid-cols-2"
            >
              <Field
                label="Name"
                icon={<IconUser />}
                value={editName}
                onChange={setEditName}
                required
              />
              <Field
                label="Phone"
                icon={<IconPhone />}
                type="tel"
                value={editPhone}
                onChange={(v) => setEditPhone(formatPhoneInput(v))}
                placeholder={PHONE_PLACEHOLDER}
              />
              <Field
                label="Email"
                icon={<IconMail />}
                type="email"
                value={editEmail}
                onChange={setEditEmail}
              />
              <Field
                label="Address"
                icon={<IconMapPin />}
                value={editAddress}
                onChange={setEditAddress}
              />
              <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
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

          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold">Vehicles</h2>
                <p className="mt-0.5 text-xs text-[var(--muted)]">
                  VIN, plate, and mileage for this customer
                </p>
              </div>
              <button
                type="button"
                onClick={openAddVehicleModal}
                className="btn-primary inline-flex items-center gap-1.5 px-4 py-2"
              >
                <IconPlus className="h-3.5 w-3.5" />
                Add
              </button>
            </div>

            {detail.vehicles.length === 0 ? (
              <div className="flex flex-col items-center rounded-xl border border-dashed border-[var(--line)] bg-[var(--background)]/50 px-6 py-10 text-center">
                <span className="mb-3 inline-flex h-11 w-11 items-center justify-center rounded-full bg-white text-[var(--muted)] ring-1 ring-[var(--line)]">
                  <IconCar className="h-5 w-5" />
                </span>
                <p className="text-sm font-medium">No vehicles yet</p>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Add a vehicle to log repair history and service visits.
                </p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {detail.vehicles.map((v) => (
                  <article
                    key={v.id}
                    className="group rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 shadow-[var(--shadow-soft)] transition hover:border-[var(--accent)]/35"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--background)] text-[var(--muted)] ring-1 ring-[var(--line)]">
                          <IconCar />
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
                    <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-lg bg-[var(--background)]/70 px-2.5 py-2">
                        <dt className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                          Plate
                        </dt>
                        <dd className="mt-0.5 font-medium">
                          {v.license_plate ?? "—"}
                        </dd>
                      </div>
                      <div className="rounded-lg bg-[var(--background)]/70 px-2.5 py-2">
                        <dt className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                          Mileage
                        </dt>
                        <dd className="mt-0.5 font-medium tabular-nums">
                          {v.mileage.toLocaleString()}
                        </dd>
                      </div>
                    </dl>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => openEditVehicleModal(v)}
                        disabled={deletingVehicleId === v.id}
                        className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium hover:border-[var(--accent)]/40 disabled:opacity-60"
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
                        className="inline-flex items-center gap-1.5 rounded-full border border-red-200 px-3 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        <IconTrash className="h-3.5 w-3.5" />
                        {deletingVehicleId === v.id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {tab === "repairs" && (
        <section className={embedded ? "-mx-4 sm:-mx-5" : "space-y-4"}>
          <div
            className={`table-scroll [scrollbar-gutter:auto] ${
              embedded ? "rounded-none border-x-0 shadow-none" : ""
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
                  <th className="px-4 py-3 sm:px-5">
                    <button
                      type="button"
                      onClick={openAddRepairModal}
                      aria-label="Add repair"
                      title="Add repair"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-[var(--line)] text-[var(--foreground)] shadow-[var(--shadow-soft)] transition hover:border-[var(--accent)]/40 hover:bg-[var(--accent)] hover:text-white"
                    >
                      <IconPlus className="h-3.5 w-3.5" />
                    </button>
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
        </section>
      )}

      {tab === "conversations" && (
        <section className="space-y-5">
          {conversationTimeline.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {voiceCalls.length > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/80 px-3 py-1 text-xs font-medium text-[var(--muted)] shadow-sm">
                  <IconPhone className="h-3 w-3" />
                  {voiceCalls.length} call{voiceCalls.length === 1 ? "" : "s"}
                </span>
              )}
              {detail.communications.length > 0 && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--line)] bg-white/80 px-3 py-1 text-xs font-medium text-[var(--muted)] shadow-sm">
                  <IconMessage className="h-3 w-3" />
                  {detail.communications.length} message
                  {detail.communications.length === 1 ? "" : "s"}
                </span>
              )}
            </div>
          )}

          {conversationTimeline.length === 0 ? (
            <div className="flex flex-col items-center rounded-xl border border-dashed border-[var(--line)] bg-[var(--background)]/50 px-6 py-12 text-center">
              <span className="mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-white text-[var(--muted)] shadow-sm ring-1 ring-[var(--line)]">
                <IconMessage className="h-5 w-5" />
              </span>
              <p className="text-sm font-medium">No conversations yet</p>
              <p className="mt-1 max-w-xs text-xs text-[var(--muted)]">
                Calls and messages will appear here once this customer starts contacting the shop.
              </p>
              <Link
                href="/dashboard/conversations?tab=calls"
                className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-[var(--accent)] hover:underline"
              >
                Open Conversations
                <IconChevronRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          ) : (
            <ol className="relative space-y-3 before:absolute before:bottom-3 before:left-[1.15rem] before:top-3 before:w-px before:bg-[var(--line)]">
              {conversationTimeline.map((item) => {
                if (item.kind === "call") {
                  const c = item.call;
                  const when = formatConversationWhen(c.started_at || c.created_at);
                  const duration = formatCallDuration(c);
                  return (
                    <li key={item.id} className="relative pl-12">
                      <span className="absolute left-0 top-3 inline-flex h-9 w-9 items-center justify-center rounded-full bg-[var(--accent)] text-white shadow-sm ring-4 ring-[var(--panel)]">
                        <IconPhone className="h-3.5 w-3.5" />
                      </span>
                      <div className="group relative rounded-xl border border-[var(--line)] bg-[var(--panel)] shadow-[var(--shadow-soft)] transition hover:border-[var(--accent)]/40 hover:shadow-md">
                        <Link
                          href={`/dashboard/conversations?tab=calls&id=${encodeURIComponent(c.id)}`}
                          className="block cursor-pointer px-4 py-3.5 pr-14"
                        >
                          <p className="text-sm font-medium tabular-nums">
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
                          aria-label="Delete call"
                          title="Delete"
                          className="absolute right-3 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-60"
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
                  <li key={item.id} className="relative pl-12">
                    <span className="absolute left-0 top-3 inline-flex h-9 w-9 items-center justify-center rounded-full border border-[var(--line)] bg-[var(--background)] text-[var(--muted)] shadow-sm ring-4 ring-[var(--panel)]">
                      <ChannelIcon className="h-3.5 w-3.5" />
                    </span>
                    <article className="flex items-start gap-2 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 shadow-[var(--shadow-soft)]">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
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
                        <p className="mt-2 text-xs text-[var(--muted)]">{when}</p>
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
                        className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-60"
                      >
                        <IconTrash className="h-3.5 w-3.5" />
                      </button>
                    </article>
                  </li>
                );
              })}
            </ol>
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
                className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
                role="dialog"
                aria-modal="true"
                aria-labelledby="add-repair-title"
                onClick={() => {
                  if (!repairSaving) closeRepairModal();
                }}
              >
                <div
                  className="flex max-h-[min(90dvh,46rem)] w-full max-w-[34rem] flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="relative shrink-0 overflow-hidden border-b border-[var(--line)] bg-gradient-to-br from-[var(--accent-soft)] via-white to-white px-5 pb-5 pt-6">
                    <div
                      className="pointer-events-none absolute right-0 top-0 h-40 w-40 translate-x-1/4 -translate-y-1/4 rounded-full bg-[var(--accent-glow)] blur-2xl"
                      aria-hidden="true"
                    />
                    <div className="relative flex min-w-0 items-center gap-3">
                      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--accent)] text-white shadow-md shadow-[var(--accent-glow)]">
                        <IconWrench className="h-4 w-4" />
                      </span>
                      <h2
                        id="add-repair-title"
                        className="text-lg font-semibold tracking-tight text-[var(--ink)]"
                      >
                        Add repair history
                      </h2>
                    </div>
                  </div>

                  {detail.vehicles.length === 0 ? (
                    <>
                      <div className="space-y-4 px-5 py-5">
                        <div className="rounded-xl border border-dashed border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-4 py-8 text-center">
                          <span className="mx-auto inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-900 text-white">
                            <IconCar className="h-5 w-5" />
                          </span>
                          <p className="mt-3 text-sm font-semibold text-slate-900">
                            Add a vehicle first
                          </p>
                          <p className="mt-1 text-sm text-[var(--muted)]">
                            Repair history is logged per vehicle.
                          </p>
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-5 py-4 sm:flex-row sm:justify-end">
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
                      <div className="asa-scroll min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-5">
                        <div className="flex items-start gap-3 rounded-xl border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-3">
                          <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
                            <IconCar className="h-4 w-4" />
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
                                <div className="grid gap-2.5 sm:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_6rem]">
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
                              rows={3}
                              placeholder="What was done (applies to all services above)"
                              className="w-full resize-y rounded-xl border border-[var(--line)] bg-white px-3 py-2.5 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                            />
                          </label>
                        </div>
                      </div>

                      <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                        <p className="text-center text-xs text-[var(--muted)] sm:text-left">
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
                        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                          <button
                            type="button"
                            onClick={closeRepairModal}
                            disabled={repairSaving}
                            className="btn-ghost inline-flex items-center justify-center gap-1.5 px-4 py-2 text-sm disabled:opacity-60"
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
                            className="btn-primary inline-flex items-center justify-center gap-1.5 px-5 py-2.5 disabled:cursor-not-allowed disabled:opacity-40"
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
            className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
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

                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
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
            className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
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
                      ? "Delete call?"
                      : "Delete message?"}
                  </h2>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                <div className="flex items-start gap-3 rounded-xl border border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-3.5 py-3">
                  <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-900 text-white">
                    {deleteConversationTarget.kind === "call" ? (
                      <IconPhone className="h-4 w-4" />
                    ) : (
                      <IconMessage className="h-4 w-4" />
                    )}
                  </span>
                  <div className="min-w-0 flex-1">
                    {deleteConversationTarget.kind === "call" ? (
                      <>
                        <p className="truncate text-sm font-semibold text-slate-900">
                          {deleteConversationTarget.call.caller_phone}
                        </p>
                        <p className="mt-1 line-clamp-2 text-xs text-[var(--muted)]">
                          {deleteConversationTarget.call.owner_summary ||
                            deleteConversationTarget.call.call_summary ||
                            deleteConversationTarget.call.last_intent ||
                            "Voice call"}
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm font-semibold text-slate-900">
                          {channelLabel(deleteConversationTarget.comm.channel)} ·{" "}
                          {deleteConversationTarget.comm.direction === "incoming"
                            ? "Inbound"
                            : "Outbound"}
                        </p>
                        <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-[var(--muted)]">
                          {deleteConversationTarget.comm.message}
                        </p>
                      </>
                    )}
                  </div>
                </div>

                <p className="text-sm leading-relaxed text-[var(--muted)]">
                  This cannot be undone. The{" "}
                  {deleteConversationTarget.kind === "call" ? "call" : "message"} will
                  be permanently removed from this customer&apos;s history.
                </p>

                {error && (
                  <p
                    className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700"
                    role="alert"
                  >
                    {error}
                  </p>
                )}

                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
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
            className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
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

                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
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
            className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
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

                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
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
            className="fixed inset-0 z-[100] flex items-end justify-center bg-slate-950/55 p-4 backdrop-blur-[2px] sm:items-center"
            role="dialog"
            aria-modal="true"
            aria-labelledby="vehicle-modal-title"
            onClick={() => {
              if (!vehicleSaving && !deletingVehicleId) closeVehicleModal();
            }}
          >
            <div
              className="flex max-h-[min(90dvh,42rem)] w-full max-w-[28rem] flex-col overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--panel)] shadow-[0_24px_64px_-16px_rgba(15,23,42,0.45)]"
              onClick={(e) => e.stopPropagation()}
            >
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
                    <div className="grid gap-3 sm:grid-cols-2">
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

                <div className="flex shrink-0 flex-col-reverse gap-2 border-t border-[var(--line)] bg-[rgba(15,23,42,0.02)] px-5 py-4 sm:flex-row sm:justify-end">
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
}: {
  label: string;
  icon?: ReactNode;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
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
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
      />
    </label>
  );
}

function RedirectToCustomerList() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();

  useEffect(() => {
    const qs = new URLSearchParams(searchParams.toString());
    qs.set("id", params.id);
    router.replace(`/dashboard/customer?${qs.toString()}`);
  }, [params.id, router, searchParams]);

  return <p className="text-sm text-[var(--muted)]">Loading customer…</p>;
}

/** Deep links `/dashboard/customer/[id]` open the list + selected detail panel. */
export default function CustomerDetailPage() {
  return (
    <Suspense
      fallback={
        <p className="text-sm text-[var(--muted)]">Loading customer…</p>
      }
    >
      <RedirectToCustomerList />
    </Suspense>
  );
}
