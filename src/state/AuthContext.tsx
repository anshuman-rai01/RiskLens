import { createContext, useCallback, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import {
  changePassword as apiChangePassword,
  ensureReady,
  forceRotate,
  getAuthSnapshot,
  login as apiLogin,
  logout as apiLogout,
  logoutEverywhere as apiLogoutEverywhere,
  register as apiRegister,
  subscribeAuth,
} from "../lib/auth";
import type { PublicUser } from "../lib/types";

type Status = "booting" | "guest" | "authed";

interface AuthCtx {
  status: Status;
  user: PublicUser | null;
  accessExp: number | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  logoutEverywhere: () => Promise<void>;
  refreshNow: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const snap = useSyncExternalStore(subscribeAuth, getAuthSnapshot);
  const [status, setStatus] = useState<Status>("booting");

  useEffect(() => {
    let mounted = true;
    ensureReady().then(() => {
      if (mounted) setStatus(getAuthSnapshot() ? "authed" : "guest");
    });
    return () => {
      mounted = false;
    };
  }, []);

  // Keep status in sync with token rotation / revocation.
  useEffect(() => {
    if (status === "booting") return;
    setStatus(snap ? "authed" : "guest");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snap]);

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password);
    setStatus("authed");
  }, []);
  const register = useCallback(async (email: string, password: string) => {
    await apiRegister(email, password);
    setStatus("authed");
  }, []);
  const logout = useCallback(async () => {
    await apiLogout();
    setStatus("guest");
  }, []);
  const logoutEverywhere = useCallback(async () => {
    await apiLogoutEverywhere();
    setStatus("guest");
  }, []);
  const refreshNow = useCallback(async () => {
    await forceRotate();
  }, []);
  const changePassword = useCallback(async (current: string, next: string) => {
    await apiChangePassword(current, next);
  }, []);

  return (
    <Ctx.Provider
      value={{
        status,
        user: snap?.user ?? null,
        accessExp: snap?.accessExp ?? null,
        login,
        register,
        logout,
        logoutEverywhere,
        refreshNow,
        changePassword,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
