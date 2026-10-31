import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, lastApiActivity, setCsrf, setSessionLostHandler } from "./api";
import { Modal } from "./components/ui";
import type { Role, Session, User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  /** Shown on the login page: why the user was signed out. */
  notice: string | null;
  idleTimeoutS: number;
  can: (permission: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  logoutAll: () => Promise<void>;
  keepAlive: () => Promise<void>;
  expire: (message: string) => void;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);

  const apply = useCallback((s: Session | null) => {
    setCsrf(s?.csrf ?? "");
    setSession(s);
  }, []);

  const expire = useCallback(
    (message: string) => {
      apply(null);
      setNotice(message);
    },
    [apply],
  );

  useEffect(() => {
    setSessionLostHandler(() => expire("Your session has expired. Please sign in again."));
    api<Session>("/auth/me")
      .then(apply)
      .catch(() => apply(null))
      .finally(() => setLoading(false));
    return () => setSessionLostHandler(null);
  }, [apply, expire]);

  const login = useCallback(
    async (email: string, password: string) => {
      apply(await api<Session>("/auth/login", { body: { email, password } }));
      setNotice(null);
    },
    [apply],
  );

  const signOut = useCallback(
    async (path: string, message: string) => {
      try {
        await api(path, { method: "POST" });
      } finally {
        apply(null);
        setNotice(message);
      }
    },
    [apply],
  );

  const keepAlive = useCallback(async () => {
    try {
      apply(await api<Session>("/auth/me"));
    } catch {
      expire("Your session has expired. Please sign in again.");
    }
  }, [apply, expire]);

  const value = useMemo<AuthState>(() => {
    const perms = new Set(session?.permissions ?? []);
    return {
      user: session?.user ?? null,
      loading,
      notice,
      idleTimeoutS: session?.idle_timeout_s ?? 1800,
      can: (p) => perms.has(p),
      login,
      logout: () => signOut("/auth/logout", "You are signed out."),
      logoutAll: () => signOut("/auth/logout-all", "You are signed out on every device."),
      keepAlive,
      expire,
    };
  }, [session, loading, notice, login, signOut, keepAlive, expire]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

/** UI hint only: the backend is the real guard and answers 403 regardless of what the UI shows. */
export function usePermission(permission: string): boolean {
  return useAuth().can(permission);
}

const WARN_BEFORE_MS = 2 * 60 * 1000;
const SERVER_SLACK_MS = 60 * 1000; // the server records activity at most once a minute

/** Warns 2 minutes before the idle timeout; signs out locally when it passes. */
export function IdleWatcher() {
  const { idleTimeoutS, keepAlive, expire } = useAuth();
  const [left, setLeft] = useState<number | null>(null);

  useEffect(() => {
    const tick = () => {
      const remaining = idleTimeoutS * 1000 - SERVER_SLACK_MS - (Date.now() - lastApiActivity());
      if (remaining <= 0) expire("You were signed out after a period of inactivity.");
      else setLeft(remaining <= WARN_BEFORE_MS ? remaining : null);
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [idleTimeoutS, expire]);

  const secs = left === null ? 0 : Math.ceil(left / 1000);
  return (
    <Modal
      open={left !== null}
      title="Are you still there?"
      onClose={() => {
        // Esc counts as "stay"; a close caused by a fresh keep-alive needs no second call
        if (Date.now() - lastApiActivity() > 5000) void keepAlive();
      }}
      actions={
        <button className="btn primary" onClick={keepAlive} autoFocus>
          Stay signed in
        </button>
      }
    >
      <p>
        For security, you will be signed out in{" "}
        <strong>
          {Math.floor(secs / 60)}:{String(secs % 60).padStart(2, "0")}
        </strong>{" "}
        unless you continue.
      </p>
    </Modal>
  );
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
