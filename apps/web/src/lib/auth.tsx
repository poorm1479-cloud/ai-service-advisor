"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AuthMethod,
  AuthSession,
  adminLogin as apiAdminLogin,
  clearSession,
  fetchMe,
  loadSession,
  login as apiLogin,
  logout as apiLogout,
  refresh as apiRefresh,
  registerShop as apiRegister,
  saveSession,
  sendOtp as apiSendOtp,
  verifyMfa as apiVerifyMfa,
} from "@/lib/api";
import { lockAdmin } from "@/lib/admin";
import { clearSetupStatusCache } from "@/lib/shopSetup";

type AuthContextValue = {
  session: AuthSession | null;
  loading: boolean;
  login: (input: {
    password: string;
    shopName: string;
    phone?: string;
    email?: string;
  }) => Promise<void>;
  adminLogin: (input: { username: string; password: string }) => Promise<void>;
  completeMfa: (input: { mfaToken: string; code: string }) => Promise<void>;
  register: (input: {
    shopName: string;
    authMethod: AuthMethod;
    ownerFullName: string;
    password: string;
    ownerPhone?: string;
    ownerEmail?: string;
  }) => Promise<void>;
  sendOtp: (input: {
    channel: AuthMethod;
    phone?: string;
    email?: string;
    purpose?: "register" | "login" | "invite";
  }) => Promise<{
    channel: AuthMethod;
    phone?: string | null;
    email?: string | null;
    dev_code?: string | null;
  }>;
  updateSession: (patch: Partial<AuthSession>) => void;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** Refresh before access token expiry so admin "online" (recent refresh) stays accurate. */
function refreshDelayMs(expiresInSec: number | undefined): number {
  const lifetimeMs = Math.max(Number(expiresInSec) || 30 * 60, 60) * 1000;
  // Refresh at ~75% of access TTL, never later than TTL − 60s.
  return Math.max(Math.min(lifetimeMs * 0.75, lifetimeMs - 60_000), 15_000);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(true);
  // Bumped on logout so in-flight refresh cannot resurrect a session.
  const authEpochRef = useRef(0);

  useLayoutEffect(() => {
    const existing = loadSession();
    if (!existing) {
      setLoading(false);
      return;
    }
    // Hydrate immediately so dashboard UI is not blocked on /auth/refresh.
    setSession(existing);
    setLoading(false);
    const epoch = authEpochRef.current;

    // Pull capabilities/role from membership (via /auth/me) so Team permission
    // edits apply without waiting for the next token refresh.
    if (existing.accountType !== "platform_admin" && existing.accessToken) {
      fetchMe(existing.accessToken)
        .then((me) => {
          if (authEpochRef.current !== epoch) return;
          setSession((prev) => {
            if (!prev || prev.accessToken !== existing.accessToken) return prev;
            const next = {
              ...prev,
              role: me.role as AuthSession["role"],
              capabilities: me.capabilities,
              fullName: me.full_name,
              phone: me.phone,
              email: me.email,
              shopName: me.shop_name,
              shopSlug: me.shop_slug,
            };
            saveSession(next);
            return next;
          });
        })
        .catch(() => {
          // Ignore — refresh below is the source of truth for auth validity.
        });
    }

    apiRefresh(existing.refreshToken)
      .then(async (next) => {
        if (authEpochRef.current !== epoch) {
          try {
            await apiLogout(next.refreshToken);
          } catch {
            // ignore — local session already cleared
          }
          return;
        }
        saveSession(next);
        setSession(next);
      })
      .catch(() => {
        if (authEpochRef.current !== epoch) return;
        clearSetupStatusCache();
        clearSession();
        setSession(null);
      });
  }, []);

  // Keep the session alive while the tab is open so presence does not flip offline
  // after the access-token window without an API 401.
  useEffect(() => {
    if (!session?.refreshToken) return;

    let cancelled = false;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let lastRefreshAt = Date.now();
    const epoch = authEpochRef.current;

    const runRefresh = async () => {
      if (inFlight) return;
      if (authEpochRef.current !== epoch) return;
      const current = loadSession();
      if (!current?.refreshToken) return;
      inFlight = true;
      try {
        const next = await apiRefresh(current.refreshToken);
        if (authEpochRef.current !== epoch) {
          // Logged out while refresh was in flight — discard the new tokens.
          try {
            await apiLogout(next.refreshToken);
          } catch {
            // ignore
          }
          return;
        }
        lastRefreshAt = Date.now();
        saveSession(next);
        if (!cancelled) setSession(next);
      } catch {
        if (authEpochRef.current !== epoch) return;
        // Only clear if the stored token still matches (another tab may have rotated).
        const latest = loadSession();
        if (latest?.refreshToken === current.refreshToken) {
          clearSession();
          if (!cancelled) setSession(null);
        } else if (latest && !cancelled) {
          setSession(latest);
        }
      } finally {
        inFlight = false;
      }
    };

    const schedule = () => {
      if (timer) clearTimeout(timer);
      const current = loadSession();
      timer = setTimeout(() => {
        void runRefresh();
      }, refreshDelayMs(current?.expiresIn ?? session.expiresIn));
    };

    schedule();

    const syncCapabilities = async () => {
      if (authEpochRef.current !== epoch) return;
      const current = loadSession();
      if (!current?.accessToken || current.accountType === "platform_admin") return;
      try {
        const me = await fetchMe(current.accessToken);
        if (authEpochRef.current !== epoch || cancelled) return;
        setSession((prev) => {
          if (!prev || prev.accessToken !== current.accessToken) return prev;
          const sameCaps =
            prev.capabilities.length === me.capabilities.length &&
            prev.capabilities.every((c, i) => c === me.capabilities[i]);
          if (sameCaps && prev.role === me.role) return prev;
          const next = {
            ...prev,
            role: me.role as AuthSession["role"],
            capabilities: me.capabilities,
          };
          saveSession(next);
          return next;
        });
      } catch {
        // Ignore — refresh handles hard auth failures.
      }
    };

    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      if (authEpochRef.current !== epoch) return;
      void syncCapabilities();
      // Background timers are throttled; refresh on return if we are past halfway to next refresh.
      const delay = refreshDelayMs(loadSession()?.expiresIn ?? session.expiresIn);
      if (Date.now() - lastRefreshAt < delay * 0.5) {
        schedule();
        return;
      }
      void runRefresh();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [session?.refreshToken, session?.expiresIn]);

  const login = useCallback(
    async (input: {
      password: string;
      shopName: string;
      phone?: string;
      email?: string;
    }) => {
      const next = await apiLogin(input);
      authEpochRef.current += 1;
      lockAdmin();
      saveSession(next);
      setSession(next);
    },
    [],
  );

  const adminLogin = useCallback(async (input: { username: string; password: string }) => {
    const next = await apiAdminLogin(input);
    authEpochRef.current += 1;
    // Gate is unlocked only after /admin/login verifies platform access.
    lockAdmin();
    saveSession(next);
    setSession(next);
  }, []);

  const completeMfa = useCallback(async (input: { mfaToken: string; code: string }) => {
    const next = await apiVerifyMfa(input);
    authEpochRef.current += 1;
    if (next.accountType !== "platform_admin") {
      lockAdmin();
    }
    saveSession(next);
    setSession(next);
  }, []);

  const register = useCallback(
    async (input: {
      shopName: string;
      authMethod: AuthMethod;
      ownerFullName: string;
      password: string;
      ownerPhone?: string;
      ownerEmail?: string;
    }) => {
      const next = await apiRegister(input);
      authEpochRef.current += 1;
      lockAdmin();
      saveSession(next);
      setSession(next);
    },
    [],
  );

  const sendOtp = useCallback(
    async (input: {
      channel: AuthMethod;
      phone?: string;
      email?: string;
      purpose?: "register" | "login" | "invite";
    }) => {
      return apiSendOtp(input);
    },
    [],
  );

  const updateSession = useCallback((patch: Partial<AuthSession>) => {
    setSession((prev) => {
      if (!prev) return prev;
      const next = { ...prev, ...patch };
      saveSession(next);
      return next;
    });
  }, []);

  const logout = useCallback(async () => {
    const current = loadSession();
    // Invalidate in-flight refresh immediately, then clear local state before the API call.
    authEpochRef.current += 1;
    lockAdmin();
    clearSetupStatusCache();
    clearSession();
    setSession(null);
    if (current?.refreshToken) {
      try {
        await apiLogout(current.refreshToken);
      } catch {
        // ignore network errors on logout
      }
    }
  }, []);

  const value = useMemo(
    () => ({
      session,
      loading,
      login,
      adminLogin,
      completeMfa,
      register,
      sendOtp,
      updateSession,
      logout,
    }),
    [session, loading, login, adminLogin, completeMfa, register, sendOtp, updateSession, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
