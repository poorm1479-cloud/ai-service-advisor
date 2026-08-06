"use client";

import Link from "next/link";
import {
  FormEvent,
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
  createVehicle,
  CustomerDetail,
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
import { listSmsConversations, SmsConversation } from "@/lib/sms";
import { listVoiceCalls, VoiceCall } from "@/lib/calls";
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

type RepairWithVehicle = RepairHistory & { vehicle_label: string };

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

function CustomerDetailContent() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const customerId = params.id;
  const { session, loading: authLoading } = useAuth();
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [repairs, setRepairs] = useState<RepairWithVehicle[]>([]);
  const [smsThreads, setSmsThreads] = useState<SmsConversation[]>([]);
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
  const [repairModalOpen, setRepairModalOpen] = useState(false);
  const [repairSaving, setRepairSaving] = useState(false);
  const [shopServices, setShopServices] = useState<ShopService[]>([]);
  const [repairVehicleId, setRepairVehicleId] = useState("");
  const [repairLines, setRepairLines] = useState<RepairServiceLine[]>([
    emptyRepairLine(),
  ]);
  const [repairDescription, setRepairDescription] = useState("");
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
      const [smsAll, callsAll] = await Promise.all([
        listSmsConversations().catch(() => [] as SmsConversation[]),
        listVoiceCalls().catch(() => [] as VoiceCall[]),
      ]);
      setSmsThreads(smsAll.filter((c) => c.customer_id === customerId));
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

        await createVehicle(customerId, {
          vin: cleanedVin || makeTempVin(),
          license_plate: plate.trim() || undefined,
          year: yearNum,
          make: make.trim() || "Unknown",
          model: model.trim() || "Unknown",
          mileage: mileageNum,
        });
        setSuccess("Vehicle added.");
      }
      setVehicleModal(null);
      resetVehicleForm();
      await load();
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

  function resetRepairForm() {
    const first = shopServices[0];
    setRepairVehicleId(detail?.vehicles[0]?.id ?? "");
    setRepairLines([
      first
        ? emptyRepairLine({
            serviceId: first.id,
            name: first.name,
            cost: formatPrice(first.price),
          })
        : emptyRepairLine(),
    ]);
    setRepairDescription("");
  }

  function openAddRepairModal() {
    setError(null);
    setSuccess(null);
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
    if (!repairVehicleId) return;

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
      router.push("/dashboard/customers");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete customer");
      setDeletingCustomer(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:h-full">
        <p className="text-sm text-[var(--muted)]">Loading customer…</p>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden md:h-full">
        <p className="text-sm text-red-700">{error ?? "Customer not found"}</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-hidden md:h-full">
      <div className="flex shrink-0 flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/dashboard/customers" className="text-sm text-[var(--muted)] hover:text-[var(--accent)]">
            ← Customers
          </Link>
          <h1 className="page-title mt-2">{detail.customer.name}</h1>
        </div>
        <div className="flex flex-wrap gap-2" role="tablist" aria-label="Customer detail sections">
          {DETAIL_TABS.map((t) => (
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

      {error &&
        !vehicleModal &&
        !repairModalOpen &&
        !deleteCustomerOpen &&
        !deleteVehicleTarget &&
        !deleteRepairTarget && (
        <p className="shrink-0 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {error}
        </p>
      )}
      {success &&
        !vehicleModal &&
        !repairModalOpen &&
        !deleteCustomerOpen &&
        !deleteVehicleTarget &&
        !deleteRepairTarget && (
        <p className="shrink-0 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800" role="status">
          {success}
        </p>
      )}

      <div className="asa-scroll min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain">
      {tab === "profile" && (
        <div className="space-y-6">
          <section className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
            <h2 className="text-sm font-semibold">Profile</h2>
            <form onSubmit={onSaveCustomer} className="mt-4 grid gap-3 sm:grid-cols-2">
              <Field label="Customer name" value={editName} onChange={setEditName} required />
              <Field
                label="Phone"
                type="tel"
                value={editPhone}
                onChange={(v) => setEditPhone(formatPhoneInput(v))}
                placeholder={PHONE_PLACEHOLDER}
              />
              <Field label="Email" type="email" value={editEmail} onChange={setEditEmail} />
              <Field label="Address" value={editAddress} onChange={setEditAddress} />
              <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
                <button
                  type="submit"
                  disabled={!profileDirty}
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Save changes
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setError(null);
                    setDeleteCustomerOpen(true);
                  }}
                  disabled={deletingCustomer}
                  className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Delete customer
                </button>
              </div>
            </form>
          </section>

          <section className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">Vehicles</h2>
              <button
                type="button"
                onClick={openAddVehicleModal}
                className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white"
              >
                Add
              </button>
            </div>
            <div className="table-scroll">
              <table>
                <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                  <tr>
                    <th className="px-4 py-3">Vehicle</th>
                    <th className="px-4 py-3">VIN</th>
                    <th className="px-4 py-3">Plate</th>
                    <th className="px-4 py-3">Mileage</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.vehicles.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-6 text-[var(--muted)]">
                        No vehicles yet
                      </td>
                    </tr>
                  ) : (
                    detail.vehicles.map((v) => (
                      <tr key={v.id} className="border-t border-[var(--line)]">
                        <td className="px-4 py-3 font-medium">{vehicleLabel(v)}</td>
                        <td className="px-4 py-3 font-mono text-xs">{v.vin}</td>
                        <td className="px-4 py-3 text-[var(--muted)]">{v.license_plate ?? "—"}</td>
                        <td className="px-4 py-3 text-[var(--muted)]">{v.mileage.toLocaleString()}</td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => openEditVehicleModal(v)}
                              disabled={deletingVehicleId === v.id}
                              className="rounded-md border border-[var(--line)] px-2.5 py-1 text-xs hover:border-[var(--accent)]/40 disabled:opacity-60"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setError(null);
                                setDeleteVehicleTarget(v);
                              }}
                              disabled={deletingVehicleId === v.id}
                              className="rounded-md border border-red-200 px-2.5 py-1 text-xs text-red-600 hover:bg-red-50 disabled:opacity-60"
                            >
                              {deletingVehicleId === v.id ? "Deleting…" : "Delete"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {tab === "repairs" && (
        <section className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Repair history</h2>
            </div>
            <button
              type="button"
              onClick={openAddRepairModal}
              disabled={detail.vehicles.length === 0}
              title={
                detail.vehicles.length === 0
                  ? "Add a vehicle before logging repair history"
                  : undefined
              }
              className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
            >
              Add
            </button>
          </div>
          <div className="table-scroll">
            <table>
              <thead className="border-b border-[var(--line)] text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                <tr>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Vehicle</th>
                  <th className="px-4 py-3">Service</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3">Cost</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {repairs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-[var(--muted)]">
                      No repair history yet
                    </td>
                  </tr>
                ) : (
                  repairs.map((r) => (
                    <tr key={r.id} className="border-t border-[var(--line)]">
                      <td className="px-4 py-3 text-sm text-[var(--muted)]">
                        {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                      </td>
                      <td className="px-4 py-3 text-sm">{r.vehicle_label}</td>
                      <td className="px-4 py-3 text-sm font-medium">{r.service_type}</td>
                      <td className="px-4 py-3 text-sm text-[var(--muted)]">{r.description}</td>
                      <td className="px-4 py-3 text-sm">${r.cost}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => {
                            setError(null);
                            setDeleteRepairTarget(r);
                          }}
                          disabled={deletingRepairId === r.id}
                          className="rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50 disabled:opacity-60"
                        >
                          Delete
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
        <section className="space-y-4">
          <h2 className="text-sm font-semibold">Conversations</h2>

          {(smsThreads.length > 0 || voiceCalls.length > 0) && (
            <div className="grid gap-3 sm:grid-cols-2">
              {smsThreads.map((t) => (
                <Link
                  key={t.id}
                  href={`/dashboard/conversations?tab=sms&id=${encodeURIComponent(t.id)}`}
                  className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 hover:border-[var(--accent)]/40"
                >
                  <div className="text-xs uppercase tracking-[0.08em] text-[var(--muted)]">SMS</div>
                  <div className="mt-1 text-sm font-medium">{t.customer_phone}</div>
                  <p className="mt-1 line-clamp-2 text-sm text-[var(--muted)]">
                    {t.owner_summary || t.reply_preview || t.last_intent || "Conversation"}
                  </p>
                  {t.last_message_at && (
                    <div className="mt-2 text-xs text-[var(--muted)]">
                      {new Date(t.last_message_at).toLocaleString()}
                    </div>
                  )}
                </Link>
              ))}
              {voiceCalls.map((c) => (
                <Link
                  key={c.id}
                  href={`/dashboard/conversations?tab=calls&id=${encodeURIComponent(c.id)}`}
                  className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4 hover:border-[var(--accent)]/40"
                >
                  <div className="text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                    Voice · {c.status}
                  </div>
                  <div className="mt-1 text-sm font-medium">{c.caller_phone}</div>
                  <p className="mt-1 line-clamp-2 text-sm text-[var(--muted)]">
                    {c.owner_summary || c.call_summary || c.last_intent || "Call"}
                  </p>
                  {c.started_at && (
                    <div className="mt-2 text-xs text-[var(--muted)]">
                      {new Date(c.started_at).toLocaleString()}
                    </div>
                  )}
                </Link>
              ))}
            </div>
          )}

          <div className="space-y-3">
            {detail.communications.length === 0 &&
            smsThreads.length === 0 &&
            voiceCalls.length === 0 ? (
              <p className="text-sm text-[var(--muted)]">No conversations yet</p>
            ) : (
              detail.communications.map((c) => (
                <div key={c.id} className="rounded-xl border border-[var(--line)] bg-[var(--panel)] p-4">
                  {c.created_at && (
                    <div className="text-xs uppercase tracking-[0.08em] text-[var(--muted)]">
                      {new Date(c.created_at).toLocaleString()}
                    </div>
                  )}
                  <p className={c.created_at ? "mt-2 text-sm" : "text-sm"}>{c.message}</p>
                </div>
              ))
            )}
          </div>
        </section>
      )}
      </div>

      {repairModalOpen &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="add-repair-title"
            onClick={closeRepairModal}
          >
            <div
              className="asa-scroll max-h-[min(90dvh,40rem)] w-full max-w-lg space-y-4 overflow-y-auto overscroll-contain rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div>
                <h2 id="add-repair-title" className="text-sm font-semibold">
                  Add repair history
                </h2>
                <p className="mt-1 text-xs text-[var(--muted)]">
                  Log completed service work for one of this customer&apos;s vehicles.
                </p>
              </div>

              {error && (
                <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                  {error}
                </p>
              )}

              {detail.vehicles.length === 0 ? (
                <p className="text-sm text-[var(--muted)]">
                  Add a vehicle on the Profile tab before logging repair history.
                </p>
              ) : (
                <form onSubmit={onAddRepair} className="grid gap-3 sm:grid-cols-2">
                  <label className="block space-y-1.5 sm:col-span-2">
                    <span className="text-sm font-medium">Vehicle</span>
                    <select
                      value={repairVehicleId}
                      required
                      onChange={(e) => setRepairVehicleId(e.target.value)}
                      className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                    >
                      {detail.vehicles.map((v) => (
                        <option key={v.id} value={v.id}>
                          {vehicleLabel(v)}
                          {v.license_plate ? ` · ${v.license_plate}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="space-y-2 sm:col-span-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium">Services</span>
                      <button
                        type="button"
                        onClick={addRepairLine}
                        className="text-sm font-medium text-[var(--accent)] hover:underline"
                      >
                        + Add service
                      </button>
                    </div>
                    <p className="text-xs text-[var(--muted)]">
                      Pick from the catalog or choose Custom and type a service name. Names and
                      costs stay editable.
                    </p>
                    {shopServices.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {shopServices.map((svc) => {
                          const selected = repairLines.some(
                            (r) => r.serviceId === svc.id || r.name.trim() === svc.name,
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
                                        r.serviceId !== svc.id && r.name.trim() !== svc.name,
                                    );
                                    return next.length > 0 ? next : [emptyRepairLine()];
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
                              className={`rounded-md border px-2.5 py-1.5 text-xs ${
                                selected
                                  ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                                  : "border-[var(--line)] text-[var(--muted)] hover:border-[var(--accent)]"
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
                          className="grid gap-2 rounded-lg border border-[var(--line)] bg-[var(--background)]/40 p-3 sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_5.5rem_auto]"
                        >
                          <label className="block space-y-1">
                            <span className="text-xs text-[var(--muted)]">
                              Catalog {index + 1}
                            </span>
                            <select
                              value={row.serviceId || (row.name ? "__custom__" : "")}
                              onChange={(e) =>
                                onRepairLineCatalogChange(row.key, e.target.value)
                              }
                              className="w-full rounded-md border border-[var(--line)] bg-white px-2.5 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
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
                            <span className="text-xs text-[var(--muted)]">Service name</span>
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
                                const matched = shopServices.find((s) => s.name === name);
                                updateRepairLine(row.key, {
                                  name,
                                  serviceId: matched?.id ?? "",
                                });
                              }}
                              placeholder="e.g. Oil Change / custom job"
                              maxLength={100}
                              className="w-full rounded-md border border-[var(--line)] bg-white px-2.5 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                            />
                          </label>
                          <label className="block space-y-1">
                            <span className="text-xs text-[var(--muted)]">Cost</span>
                            <input
                              type="number"
                              min={0}
                              step="0.01"
                              value={row.cost}
                              required={Boolean(row.name.trim())}
                              onChange={(e) =>
                                updateRepairLine(row.key, { cost: e.target.value })
                              }
                              placeholder="0.00"
                              className="w-full rounded-md border border-[var(--line)] bg-white px-2.5 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                            />
                          </label>
                          <div className="flex items-end">
                            <button
                              type="button"
                              onClick={() => removeRepairLine(row.key)}
                              disabled={repairLines.length <= 1}
                              className="w-full rounded-md border border-[var(--line)] px-2.5 py-2 text-sm text-[var(--muted)] hover:border-red-300 hover:text-red-700 disabled:cursor-not-allowed disabled:opacity-40 sm:w-auto"
                              aria-label={`Remove service ${index + 1}`}
                            >
                              Remove
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                    {shopServices.length === 0 && (
                      <p className="text-xs text-[var(--muted)]">
                        No catalog services yet — type a custom name, or add services in{" "}
                        <Link
                          href="/dashboard/services"
                          className="text-[var(--accent)] hover:underline"
                        >
                          Service Catalog
                        </Link>
                        .
                      </p>
                    )}
                  </div>
                  <label className="block space-y-1.5 sm:col-span-2">
                    <span className="text-sm font-medium">Description</span>
                    <textarea
                      value={repairDescription}
                      onChange={(e) => setRepairDescription(e.target.value)}
                      rows={3}
                      placeholder="What was done (applies to all services above)"
                      className="w-full rounded-md border border-[var(--line)] bg-white px-3 py-2 text-sm outline-none ring-[var(--accent)] focus:ring-2"
                    />
                  </label>
                  <div className="flex flex-wrap gap-2 sm:col-span-2">
                    <button
                      type="submit"
                      disabled={
                        repairSaving ||
                        !repairVehicleId ||
                        !repairLines.some((r) => r.name.trim())
                      }
                      className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {repairSaving ? "Saving…" : "Save"}
                    </button>
                    <button
                      type="button"
                      onClick={closeRepairModal}
                      disabled={repairSaving}
                      className="rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>,
          document.body,
        )}

      {deleteRepairTarget &&
        createPortal(
          <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-repair-title"
            onClick={() => {
              if (!deletingRepairId) setDeleteRepairTarget(null);
            }}
          >
            <div
              className="w-full max-w-md space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div>
                <h2 id="delete-repair-title" className="text-sm font-semibold text-red-700">
                  Delete repair history?
                </h2>
                <p className="mt-2 text-sm text-[var(--muted)]">
                  Remove{" "}
                  <span className="font-medium text-[var(--foreground)]">
                    {deleteRepairTarget.service_type}
                  </span>{" "}
                  for {deleteRepairTarget.vehicle_label}. This cannot be undone.
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
                  onClick={() => setDeleteRepairTarget(null)}
                  disabled={!!deletingRepairId}
                  className="rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
                >
                  No
                </button>
                <button
                  type="button"
                  onClick={() => void onConfirmDeleteRepair()}
                  disabled={!!deletingRepairId}
                  className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
                >
                  {deletingRepairId ? "Deleting…" : "Yes"}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {deleteVehicleTarget && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-vehicle-title"
          onClick={() => {
            if (!deletingVehicleId) setDeleteVehicleTarget(null);
          }}
        >
          <div
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="delete-vehicle-title" className="text-sm font-semibold text-red-700">
                Delete {vehicleLabel(deleteVehicleTarget)}?
              </h2>
              <p className="mt-2 text-sm text-[var(--muted)]">
                Repair history for this vehicle will be removed. This cannot be undone.
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
                onClick={() => setDeleteVehicleTarget(null)}
                disabled={!!deletingVehicleId}
                className="rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
              >
                No
              </button>
              <button
                type="button"
                onClick={() => void onConfirmDeleteVehicle()}
                disabled={!!deletingVehicleId}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {deletingVehicleId ? "Deleting…" : "Yes"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteCustomerOpen && detail && (
        <div
          className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-customer-title"
          onClick={() => {
            if (!deletingCustomer) setDeleteCustomerOpen(false);
          }}
        >
          <div
            className="w-full max-w-md space-y-4 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="delete-customer-title" className="text-sm font-semibold text-red-700">
                Delete {detail.customer.name}?
              </h2>
              <p className="mt-2 text-sm text-[var(--muted)]">
                This permanently removes all of their data — vehicles, repair history,
                communications, appointments, SMS, and calls. This cannot be undone.
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
                onClick={() => setDeleteCustomerOpen(false)}
                disabled={deletingCustomer}
                className="rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
              >
                No
              </button>
              <button
                type="button"
                onClick={() => void onConfirmDeleteCustomer()}
                disabled={deletingCustomer}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
              >
                {deletingCustomer ? "Deleting…" : "Yes"}
              </button>
            </div>
          </div>
        </div>
      )}

      {vehicleModal && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="vehicle-modal-title"
          onClick={closeVehicleModal}
        >
          <div
            className="asa-scroll max-h-[min(90dvh,40rem)] w-full max-w-lg space-y-4 overflow-y-auto overscroll-contain rounded-xl border border-[var(--line)] bg-[var(--panel)] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div>
              <h2 id="vehicle-modal-title" className="text-sm font-semibold">
                {vehicleModal === "edit" ? "Edit vehicle" : "Add vehicle"}
              </h2>
              <p className="mt-1 text-xs text-[var(--muted)]">
                {vehicleModal === "edit"
                  ? "Update VIN, plate, year, make, model, or mileage."
                  : "Enter a 17-character VIN to auto-fill year, make, and model. Or enter any detail manually; a temporary VIN is used when VIN is blank."}
              </p>
            </div>

            {error && (
              <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {error}
              </p>
            )}

            <form onSubmit={onSaveVehicle} className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <VinInput
                  value={vin}
                  onChange={setVin}
                  status={vinStatus}
                  looking={vinLooking}
                  required={vehicleModal === "edit"}
                />
              </div>
              <Field label="License plate" value={plate} onChange={setPlate} placeholder="Optional" />
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
              <div className="flex flex-wrap gap-2 sm:col-span-2">
                <button
                  type="submit"
                  disabled={
                    vehicleSaving ||
                    Boolean(deletingVehicleId) ||
                    (vehicleModal === "edit" && !vehicleDirty) ||
                    (vehicleModal === "add" &&
                      ![vin, plate, year, make, model, mileage].some((v) => v.trim().length > 0))
                  }
                  className="rounded-md bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {vehicleSaving
                    ? "Saving…"
                    : vehicleModal === "edit"
                      ? "Save changes"
                      : "Save"}
                </button>
                <button
                  type="button"
                  onClick={closeVehicleModal}
                  disabled={vehicleSaving || Boolean(deletingVehicleId)}
                  className="rounded-md border border-[var(--line)] px-4 py-2 text-sm disabled:opacity-60"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  required?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
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

export default function CustomerDetailPage() {
  return (
    <Suspense
      fallback={
        <p className="text-sm text-[var(--muted)]">Loading customer…</p>
      }
    >
      <CustomerDetailContent />
    </Suspense>
  );
}
