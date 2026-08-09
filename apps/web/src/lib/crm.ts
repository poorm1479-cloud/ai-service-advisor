import { AuthSession, getApiUrl, loadSession, refresh, saveSession, clearSession } from "@/lib/api";

export type Customer = {
  id: string;
  shop_id: string;
  name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  created_at?: string | null;
};

export type Vehicle = {
  id: string;
  shop_id: string;
  customer_id: string | null;
  vin: string;
  license_plate: string | null;
  year: number;
  make: string;
  model: string;
  mileage: number;
  created_at?: string | null;
};

export type RepairHistory = {
  id: string;
  shop_id: string;
  customer_id: string | null;
  vehicle_id: string;
  service_type: string;
  description: string;
  cost: string;
  recommendation: string | null;
  created_at?: string | null;
};

export type Communication = {
  id: string;
  shop_id: string;
  customer_id: string;
  channel: "phone" | "sms" | "email" | "facebook";
  message: string;
  direction: "incoming" | "outgoing";
  created_at?: string | null;
};

export type CustomerDetail = {
  customer: Customer;
  vehicles: Vehicle[];
  communications: Communication[];
  repair_history?: RepairHistory[];
};

export type VehicleDetail = {
  vehicle: Vehicle;
  repair_history: RepairHistory[];
};

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg ?? "Invalid").join(", ");
    }
    return res.statusText || "Request failed";
  } catch {
    return res.statusText || "Request failed";
  }
}

async function authFetch(path: string, init: RequestInit = {}, session?: AuthSession | null) {
  let current = session ?? loadSession();
  if (!current) throw new Error("Not authenticated");

  const doFetch = (accessToken: string) =>
    fetch(`${getApiUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(init.headers ?? {}),
      },
    });

  let res = await doFetch(current.accessToken);
  if (res.status === 401) {
    try {
      current = await refresh(current.refreshToken);
      saveSession(current);
      res = await doFetch(current.accessToken);
    } catch {
      clearSession();
      throw new Error("Session expired");
    }
  }
  return res;
}

export async function searchCustomers(q?: string): Promise<Customer[]> {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  const res = await authFetch(`/v1/customers${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export type CustomerDirectoryItem = {
  customer: Customer;
  vehicles: Vehicle[];
  last_service: RepairHistory | null;
};

export async function listCustomerDirectory(q?: string): Promise<CustomerDirectoryItem[]> {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  const res = await authFetch(`/v1/customers/directory${qs}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function createCustomer(input: {
  name: string;
  phone?: string;
  email?: string;
  address?: string;
}): Promise<Customer> {
  const res = await authFetch("/v1/customers", {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateCustomer(
  id: string,
  input: Partial<{
    name: string;
    phone: string | null;
    email: string | null;
    address: string | null;
  }>,
): Promise<Customer> {
  const res = await authFetch(`/v1/customers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getCustomerDetail(id: string): Promise<CustomerDetail> {
  const res = await authFetch(`/v1/customers/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteCustomer(id: string): Promise<void> {
  const res = await authFetch(`/v1/customers/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function createVehicle(
  customerId: string,
  input: {
    vin: string;
    license_plate?: string;
    year: number;
    make: string;
    model: string;
    mileage: number;
  },
): Promise<Vehicle> {
  const res = await authFetch(`/v1/customers/${customerId}/vehicles`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateVehicle(
  vehicleId: string,
  input: Partial<{
    vin: string;
    license_plate: string | null;
    year: number;
    make: string;
    model: string;
    mileage: number;
  }>,
): Promise<Vehicle> {
  const res = await authFetch(`/v1/vehicles/${vehicleId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteVehicle(vehicleId: string): Promise<void> {
  const res = await authFetch(`/v1/vehicles/${vehicleId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function addCommunication(
  customerId: string,
  input: {
    channel: Communication["channel"];
    direction: Communication["direction"];
    message: string;
  },
): Promise<Communication> {
  const res = await authFetch(`/v1/customers/${customerId}/communications`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteCommunication(
  customerId: string,
  communicationId: string,
): Promise<void> {
  const res = await authFetch(
    `/v1/customers/${customerId}/communications/${communicationId}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(await parseError(res));
}

export async function getVehicleDetail(id: string): Promise<VehicleDetail> {
  const res = await authFetch(`/v1/vehicles/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function addRepairHistory(
  vehicleId: string,
  input: {
    service_type: string;
    description: string;
    cost: number;
    recommendation?: string;
  },
): Promise<RepairHistory> {
  const res = await authFetch(`/v1/vehicles/${vehicleId}/history`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function deleteRepairHistory(
  vehicleId: string,
  repairId: string,
): Promise<void> {
  const res = await authFetch(`/v1/vehicles/${vehicleId}/history/${repairId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
}
