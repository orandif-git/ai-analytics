import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, hasToken, setToken } from "./api";
import type { Me } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(hasToken());

  const load = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/auth/me"));
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (hasToken()) void load();
    const onUnauthorized = () => setMe(null);
    window.addEventListener("aia-unauthorized", onUnauthorized);
    return () => window.removeEventListener("aia-unauthorized", onUnauthorized);
  }, [load]);

  const login = async (email: string, password: string) => {
    const r = await api.post<{ access_token: string }>("/auth/login", { email, password });
    setToken(r.access_token);
    await load();
  };
  const logout = () => {
    setToken(null);
    setMe(null);
  };

  return <Ctx.Provider value={{ me, loading, login, logout }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

export const isTenantAdmin = (me: Me | null) => me?.role === "owner" || me?.role === "admin";
