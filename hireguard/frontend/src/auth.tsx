import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, setCsrf } from "./api";
import type { Role, User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<{ user: User; csrf: string }>("/auth/me")
      .then((r) => {
        setCsrf(r.csrf);
        setUser(r.user);
      })
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const r = await api<{ user: User; csrf: string }>("/auth/login", { body: { email, password } });
    setCsrf(r.csrf);
    setUser(r.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setCsrf("");
      setUser(null);
    }
  }, []);

  return <Ctx.Provider value={{ user, loading, login, logout }}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

export function hasRole(user: User | null, ...roles: Role[]) {
  return !!user && roles.includes(user.role);
}

export const ROLE_LABEL: Record<Role, string> = {
  recruiter: "Recruiter",
  hr_manager: "HR Manager",
  employee: "Employee",
  admin: "Admin",
};
