import { getLocalTimezone } from "@/lib/timezone";

export type UserRole = "owner" | "staff" | "ai_agent";

export type SessionRole = UserRole | "platform_admin";

export type AccountType = "shop" | "platform_admin";

/** @deprecated Legacy job-title roles â€” accepted from old sessions and mapped to staff. */
export type LegacyUserRole = "manager" | "service_advisor" | "mechanic" | "receptionist" | "technician";

export type StaffCapability =
  | "customer_management"
  | "vehicle_management"
  | "appointment_management"
  | "inspection_input"
  | "estimate_creation"
  | "repair_status_update"
  | "customer_communication"
  | "payment_handling";

export type AuthMethod = "phone" | "email";

export type AuthSession = {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  userId: string;
  shopId: string | null;
  role: SessionRole;
  accountType: AccountType;
  capabilities: StaffCapability[];
  primaryAuthMethod: AuthMethod;
  username: string | null;
  phone: string | null;
  email: string | null;
  fullName: string;
  shopName: string;
  shopSlug: string;
};

export type MeResponse = {
  user_id: string;
  primary_auth_method: AuthMethod;
  username: string | null;
  phone: string | null;
  email: string | null;
  full_name: string;
  shop_id: string;
  shop_name: string;
  shop_slug: string;
  role: UserRole;
  capabilities: StaffCapability[];
  phone_verified: boolean;
  email_verified: boolean;
};

export type RememberedLogin = {
  shopName: string;
  /** @deprecated Preferred key is shopName; kept for older localStorage drafts. */
  shopSlug?: string;
  method: AuthMethod;
  phone?: string;
  email?: string;
};

export type RememberedRegister = {
  authMethod: AuthMethod;
  shopName: string;
  ownerFullName: string;
  ownerPhone?: string;
  ownerEmail?: string;
  password?: string;
  /** @deprecated No longer collected; ignored if present in old drafts. */
  shopSlug?: string;
};

/** Per-method signup drafts so email data cannot leak into phone (and vice versa). */
export type RememberedRegisterStore = {
  lastMethod: AuthMethod;
  phone?: RememberedRegister;
  email?: RememberedRegister;
};

const CONFIGURED_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const STORAGE_KEY = "asa.auth.v1";
const REMEMBER_KEY = "asa.login.remember.v1";
const LOGIN_PASSWORD_KEY = "asa.login.password.v1";
const REGISTER_REMEMBER_KEY = "asa.register.remember.v2";
const REGISTER_REMEMBER_KEY_LEGACY = "asa.register.remember.v1";
const REGISTER_PASSWORD_KEY_LEGACY = "asa.register.password.v1";

function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

/**
 * Browser API base URL.
 * Prefer the Next.js same-origin rewrite (/api-backend) whenever the
 * configured API host is loopback, so the browser never needs to open
 * :8000 directly (Astrill/VPN and some Windows setups block that even
 * when the API process is healthy).
 */
export function getApiUrl() {
  if (typeof window !== "undefined") {
    let configuredHost = "";
    try {
      configuredHost = new URL(CONFIGURED_API_URL).hostname;
    } catch {
      configuredHost = "";
    }
    if (!configuredHost || isLoopbackHost(configuredHost)) {
      return `${window.location.origin}/api-backend`;
    }
  }
  return CONFIGURED_API_URL;
}

export function loadSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as AuthSession & {
      role?: string;
      primary_auth_method?: string;
      account_type?: string;
      accountType?: string;
    };
    return {
      ...parsed,
      shopId: parsed.shopId || null,
      role: normalizeSessionRole(parsed.role),
      accountType: normalizeAccountType(parsed.accountType ?? parsed.account_type ?? parsed.role),
      primaryAuthMethod:
        parsed.primaryAuthMethod === "email" || parsed.primary_auth_method === "email"
          ? "email"
          : "phone",
      username: parsed.username ?? null,
      phone: parsed.phone || null,
      email: parsed.email ?? null,
      shopName: parsed.shopName || "",
      shopSlug: parsed.shopSlug || "",
      capabilities: Array.isArray(parsed.capabilities) ? parsed.capabilities : [],
    };
  } catch {
    return null;
  }
}

export function saveSession(session: AuthSession) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession() {
  localStorage.removeItem(STORAGE_KEY);
}

export function loadRememberedLogin(): RememberedLogin | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(REMEMBER_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as RememberedLogin;
    const shopName = (parsed.shopName || parsed.shopSlug || "").trim();
    if (!shopName || (parsed.method !== "phone" && parsed.method !== "email")) return null;
    return {
      shopName,
      shopSlug: parsed.shopSlug,
      method: parsed.method,
      phone: parsed.phone,
      email: parsed.email,
    };
  } catch {
    return null;
  }
}

export function saveRememberedLogin(value: RememberedLogin) {
  localStorage.setItem(REMEMBER_KEY, JSON.stringify(value));
}

export function clearRememberedLogin() {
  localStorage.removeItem(REMEMBER_KEY);
}

export function loadRememberedLoginPassword(): string | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(LOGIN_PASSWORD_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { password?: string };
    return typeof parsed.password === "string" && parsed.password ? parsed.password : null;
  } catch {
    return null;
  }
}

export function saveRememberedLoginPassword(password: string) {
  localStorage.setItem(LOGIN_PASSWORD_KEY, JSON.stringify({ password }));
}

export function clearRememberedLoginPassword() {
  localStorage.removeItem(LOGIN_PASSWORD_KEY);
}

function normalizeRememberedRegister(
  value: Partial<RememberedRegister> | null | undefined,
  fallbackMethod: AuthMethod,
): RememberedRegister | null {
  if (!value) return null;
  const authMethod =
    value.authMethod === "phone" || value.authMethod === "email" ? value.authMethod : fallbackMethod;
  const shopName = value.shopName ?? "";
  const ownerFullName = value.ownerFullName ?? "";
  const ownerPhone = authMethod === "phone" ? value.ownerPhone : undefined;
  const ownerEmail = authMethod === "email" ? value.ownerEmail : undefined;
  const password = typeof value.password === "string" && value.password ? value.password : undefined;
  // Ignore empty shells created by method switches / autofill noise.
  if (!shopName && !ownerFullName && !ownerPhone && !ownerEmail && !password) {
    return null;
  }
  return {
    authMethod,
    shopName,
    ownerFullName,
    ownerPhone,
    ownerEmail,
    password,
  };
}

/** Drop phone/email drafts that were polluted by the other method's credentials. */
export function sanitizeRememberedRegisterStore(
  store: RememberedRegisterStore,
): RememberedRegisterStore | null {
  let phone = normalizeRememberedRegister(store.phone, "phone") ?? undefined;
  const email = normalizeRememberedRegister(store.email, "email") ?? undefined;

  if (phone && email) {
    const sameShop = Boolean(phone.shopName && phone.shopName === email.shopName);
    const samePassword = Boolean(phone.password && phone.password === email.password);
    const phoneHasContact = Boolean(phone.ownerPhone && phone.ownerPhone.trim());
    // If phone draft is just a copy of email credentials (typical autofill leak), discard it.
    if ((sameShop || samePassword) && !phoneHasContact) {
      phone = undefined;
    }
  }

  if (!phone && !email) return null;
  const requested = store.lastMethod === "email" ? "email" : "phone";
  const lastMethod =
    requested === "email" && email ? "email" : requested === "phone" && phone ? "phone" : email ? "email" : "phone";
  return { lastMethod, phone, email };
}

function loadLegacyRememberedRegisterStore(): RememberedRegisterStore | null {
  const raw = localStorage.getItem(REGISTER_REMEMBER_KEY_LEGACY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as RememberedRegister;
    const draft = normalizeRememberedRegister(parsed, "phone");
    if (!draft) return null;
    const passwordRaw = localStorage.getItem(REGISTER_PASSWORD_KEY_LEGACY);
    if (passwordRaw) {
      try {
        const passwordParsed = JSON.parse(passwordRaw) as { password?: string };
        if (typeof passwordParsed.password === "string" && passwordParsed.password) {
          draft.password = passwordParsed.password;
        }
      } catch {
        // ignore legacy password parse errors
      }
    }
    return {
      lastMethod: draft.authMethod,
      [draft.authMethod]: draft,
    };
  } catch {
    return null;
  }
}

export function loadRememberedRegisterStore(): RememberedRegisterStore | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(REGISTER_REMEMBER_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as RememberedRegisterStore;
      const sanitized = sanitizeRememberedRegisterStore({
        lastMethod: parsed.lastMethod === "email" ? "email" : "phone",
        phone: parsed.phone,
        email: parsed.email,
      });
      if (sanitized) {
        // Persist cleanup so polluted phone drafts do not keep coming back.
        localStorage.setItem(REGISTER_REMEMBER_KEY, JSON.stringify(sanitized));
      } else {
        localStorage.removeItem(REGISTER_REMEMBER_KEY);
      }
      return sanitized;
    } catch {
      // fall through to legacy
    }
  }
  const legacy = loadLegacyRememberedRegisterStore();
  if (legacy) {
    const sanitized = sanitizeRememberedRegisterStore(legacy);
    if (sanitized) saveRememberedRegisterStore(sanitized);
    localStorage.removeItem(REGISTER_REMEMBER_KEY_LEGACY);
    localStorage.removeItem(REGISTER_PASSWORD_KEY_LEGACY);
    return sanitized;
  }
  return null;
}

export function saveRememberedRegisterStore(store: RememberedRegisterStore) {
  const sanitized = sanitizeRememberedRegisterStore(store);
  if (!sanitized) {
    clearRememberedRegister();
    return;
  }
  localStorage.setItem(REGISTER_REMEMBER_KEY, JSON.stringify(sanitized));
  localStorage.removeItem(REGISTER_REMEMBER_KEY_LEGACY);
  localStorage.removeItem(REGISTER_PASSWORD_KEY_LEGACY);
}

/** Loads the last-used method draft. Prefer loadRememberedRegisterStore for per-method access. */
export function loadRememberedRegister(): RememberedRegister | null {
  const store = loadRememberedRegisterStore();
  if (!store) return null;
  return store[store.lastMethod] ?? store.phone ?? store.email ?? null;
}

export function saveRememberedRegister(value: RememberedRegister) {
  const store = loadRememberedRegisterStore() ?? { lastMethod: value.authMethod };
  const draft = normalizeRememberedRegister(value, value.authMethod);
  if (!draft) return;
  saveRememberedRegisterStore({
    ...store,
    lastMethod: draft.authMethod,
    [draft.authMethod]: draft,
  });
}

export function clearRememberedRegister() {
  localStorage.removeItem(REGISTER_REMEMBER_KEY);
  localStorage.removeItem(REGISTER_REMEMBER_KEY_LEGACY);
  localStorage.removeItem(REGISTER_PASSWORD_KEY_LEGACY);
}

/** @deprecated Password is stored per-method inside RememberedRegisterStore. */
export function loadRememberedRegisterPassword(): string | null {
  const remembered = loadRememberedRegister();
  return remembered?.password ?? null;
}

/** @deprecated Password is stored per-method inside RememberedRegisterStore. */
export function saveRememberedRegisterPassword(password: string) {
  const remembered = loadRememberedRegister();
  if (!remembered) return;
  saveRememberedRegister({ ...remembered, password });
}

export function clearRememberedRegisterPassword() {
  const store = loadRememberedRegisterStore();
  if (!store) {
    localStorage.removeItem(REGISTER_PASSWORD_KEY_LEGACY);
    return;
  }
  saveRememberedRegisterStore({
    ...store,
    phone: store.phone ? { ...store.phone, password: undefined } : undefined,
    email: store.email ? { ...store.email, password: undefined } : undefined,
  });
}

function normalizeRole(raw: unknown): UserRole {
  const value = String(raw ?? "").toLowerCase();
  if (value === "owner") return "owner";
  if (value === "ai_agent" || value === "ai-agent" || value === "agent") return "ai_agent";
  // staff + all legacy job titles
  return "staff";
}

function normalizeSessionRole(raw: unknown): SessionRole {
  const value = String(raw ?? "").toLowerCase();
  if (value === "platform_admin") return "platform_admin";
  return normalizeRole(raw);
}

function normalizeAccountType(raw: unknown): AccountType {
  const value = String(raw ?? "").toLowerCase();
  if (value === "platform_admin") return "platform_admin";
  return "shop";
}

function mapTokenResponse(data: Record<string, unknown>): AuthSession {
  const caps = Array.isArray(data.capabilities)
    ? (data.capabilities as StaffCapability[])
    : [];
  const role = normalizeSessionRole(data.role);
  const accountType = normalizeAccountType(data.account_type ?? data.role);
  return {
    accessToken: String(data.access_token),
    refreshToken: String(data.refresh_token),
    expiresIn: Number(data.expires_in),
    userId: String(data.user_id),
    shopId: data.shop_id ? String(data.shop_id) : null,
    role,
    accountType,
    capabilities: caps,
    primaryAuthMethod: data.primary_auth_method === "email" ? "email" : "phone",
    username: data.username ? String(data.username) : null,
    phone: data.phone ? String(data.phone) : null,
    email: data.email ? String(data.email) : null,
    fullName: String(data.full_name),
    shopName: data.shop_name ? String(data.shop_name) : "",
    shopSlug: data.shop_slug ? String(data.shop_slug) : "",
  };
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (body.detail && typeof body.detail === "object" && !Array.isArray(body.detail)) {
      const message = (body.detail as { message?: unknown }).message;
      if (typeof message === "string" && message) return message;
    }
    if (Array.isArray(body.detail)) {
      return (
        body.detail
          .map((d: { loc?: unknown[]; msg?: string; type?: string }) => {
            const field = Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1] ?? "") : "";
            if (field === "shop_name") {
              return "Enter your shop name.";
            }
            if (field === "shop_slug") {
              return "Shop could not be identified. Check the shop name.";
            }
            if (field === "owner_phone") {
              return "Enter a valid phone number.";
            }
            if (field === "owner_email") {
              return "Enter a valid email address.";
            }
            if (field === "password") {
              return "Password must be at least 8 characters.";
            }
            return d?.msg;
          })
          .filter(Boolean)
          .join("; ") || res.statusText
      );
    }
    return res.statusText || "Request failed";
  } catch {
    return res.statusText || "Request failed";
  }
}

async function parseAdminLoginError(res: Response): Promise<Error> {
  let body: { detail?: unknown } = {};
  try {
    body = await res.json();
  } catch {
    body = {};
  }
  const detail = body.detail;
  let message = res.statusText || "Login failed";
  let retryAfter: number | null = null;
  if (typeof detail === "string") {
    message = detail;
  } else if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const obj = detail as { message?: unknown; retry_after?: unknown };
    if (typeof obj.message === "string" && obj.message) message = obj.message;
    if (typeof obj.retry_after === "number" && Number.isFinite(obj.retry_after)) {
      retryAfter = Math.max(0, Math.ceil(obj.retry_after));
    }
  }
  if (retryAfter == null) {
    const header = Number(res.headers.get("Retry-After") || "");
    if (Number.isFinite(header) && header > 0) retryAfter = Math.ceil(header);
  }
  if (res.status === 429 || (retryAfter != null && retryAfter > 0)) {
    return new AdminLoginLockoutError(message, retryAfter ?? 600);
  }
  return new Error(message || "Login failed");
}

export async function sendOtp(input: {
  channel: AuthMethod;
  phone?: string;
  email?: string;
  purpose?: "register" | "login" | "invite";
}): Promise<{
  channel: AuthMethod;
  phone?: string | null;
  email?: string | null;
  purpose: string;
  expires_in: number;
  resend_after: number;
  challenge_id: string;
  dev_code?: string | null;
}> {
  const res = await fetch(`${getApiUrl()}/v1/auth/otp/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channel: input.channel,
      phone: input.phone || null,
      email: input.email || null,
      purpose: input.purpose ?? "register",
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function verifyOtp(input: {
  channel: AuthMethod;
  phone?: string;
  email?: string;
  code: string;
  purpose?: "register" | "login" | "invite";
}): Promise<{ ok: boolean; channel: AuthMethod; phone?: string | null; email?: string | null }> {
  const res = await fetch(`${getApiUrl()}/v1/auth/otp/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channel: input.channel,
      phone: input.phone || null,
      email: input.email || null,
      code: input.code,
      purpose: input.purpose ?? "register",
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function registerShop(input: {
  shopName: string;
  authMethod: AuthMethod;
  ownerFullName: string;
  password: string;
  ownerPhone?: string;
  ownerEmail?: string;
  timezone?: string;
}): Promise<AuthSession> {
  const payload = {
    shop_name: input.shopName,
    auth_method: input.authMethod,
    owner_full_name: input.ownerFullName,
    password: input.password,
    owner_phone: input.ownerPhone || null,
    owner_email: input.ownerEmail || null,
    timezone: input.timezone || getLocalTimezone(),
  };

  async function post(path: string): Promise<Response> {
    const apiUrl = getApiUrl();
    try {
      return await fetch(`${apiUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch {
      throw new Error(
        `Cannot reach API at ${apiUrl}. Start the API (port 8000), then try again.`,
      );
    }
  }

  let res = await post("/v1/auth/register");
  if (res.status === 404) {
    res = await post("/v1/auth/register-shop");
  }
  if (!res.ok) throw new Error(await parseError(res));
  return mapTokenResponse(await res.json());
}

export class MfaRequiredError extends Error {
  mfaToken: string;
  constructor(mfaToken: string) {
    super("MFA required");
    this.name = "MfaRequiredError";
    this.mfaToken = mfaToken;
  }
}

export class AdminLoginLockoutError extends Error {
  retryAfterSeconds: number;
  constructor(message: string, retryAfterSeconds: number) {
    super(message);
    this.name = "AdminLoginLockoutError";
    this.retryAfterSeconds = Math.max(0, Math.ceil(retryAfterSeconds));
  }
}

export async function login(input: {
  password: string;
  shopName: string;
  phone?: string;
  email?: string;
}): Promise<AuthSession> {
  const apiUrl = getApiUrl();
  let res: Response;
  try {
    res = await fetch(`${apiUrl}/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        phone: input.phone || null,
        email: input.email || null,
        password: input.password,
        shop_name: input.shopName,
      }),
    });
  } catch {
    throw new Error(`Cannot reach API at ${apiUrl}. Start the API (port 8000), then try again.`);
  }
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  if (data.mfa_required && data.mfa_token) {
    throw new MfaRequiredError(String(data.mfa_token));
  }
  return mapTokenResponse(data);
}

export async function adminLogin(input: {
  username: string;
  password: string;
}): Promise<AuthSession> {
  const apiUrl = getApiUrl();
  let res: Response;
  try {
    res = await fetch(`${apiUrl}/v1/auth/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: input.username.trim().toLowerCase(),
        password: input.password,
      }),
    });
  } catch {
    throw new Error(`Cannot reach API at ${apiUrl}. Start the API (port 8000), then try again.`);
  }
  if (!res.ok) throw await parseAdminLoginError(res);
  const data = await res.json();
  if (data.mfa_required && data.mfa_token) {
    throw new MfaRequiredError(String(data.mfa_token));
  }
  return mapTokenResponse(data);
}

export async function verifyMfa(input: { mfaToken: string; code: string }): Promise<AuthSession> {
  const res = await fetch(`${getApiUrl()}/v1/auth/mfa/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mfa_token: input.mfaToken, code: input.code }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return mapTokenResponse(await res.json());
}

export async function refresh(refreshToken: string): Promise<AuthSession> {
  const res = await fetch(`${getApiUrl()}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return mapTokenResponse(await res.json());
}

export async function logout(refreshToken: string): Promise<void> {
  await fetch(`${getApiUrl()}/v1/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
}

export async function fetchMe(accessToken: string): Promise<MeResponse> {
  const res = await fetch(`${getApiUrl()}/v1/auth/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export const ROLE_LABELS: Record<SessionRole, string> = {
  owner: "Owner",
  staff: "Staff",
  ai_agent: "AI Agent",
  platform_admin: "Platform Admin",
};

export const CAPABILITY_LABELS: Record<StaffCapability, string> = {
  customer_management: "Customer Records",
  vehicle_management: "Vehicle Records",
  appointment_management: "Appointments",
  inspection_input: "Inspection",
  estimate_creation: "Estimates",
  repair_status_update: "Repair Updates",
  customer_communication: "Calls & Messages",
  payment_handling: "Payments",
};
