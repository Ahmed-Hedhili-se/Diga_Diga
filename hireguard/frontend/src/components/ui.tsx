import { ReactNode, useCallback, useEffect, useState } from "react";
import { errMsg } from "../api";

export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(() => {
    setLoading(true);
    fn()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(errMsg(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(reload, [reload]);
  return { data, error, loading, reload, setData };
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="alert danger">{error}</div>;
}

export function Loading({ show }: { show: boolean }) {
  return show ? <div className="muted">Loading…</div> : null;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty muted">{children}</div>;
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "ok" | "warn" | "danger" | "info"; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function fmtDate(s?: string | null) {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleString();
}

export function fmtNum(n: number | undefined | null, digits = 0) {
  if (n === undefined || n === null || isNaN(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

/** Render any value as plain text (never HTML). */
export function plain(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

const INVISIBLE: Record<string, string> = {
  "​": "⟨ZWSP⟩",
  "‌": "⟨ZWNJ⟩",
  "‍": "⟨ZWJ⟩",
  "⁠": "⟨WJ⟩",
  "﻿": "⟨BOM⟩",
  "­": "⟨SHY⟩",
  "‮": "⟨RLO⟩",
  "‭": "⟨LRO⟩",
};

/** Make zero-width / bidi control characters visible for the Security Center. */
export function revealInvisible(s: string): string {
  return s.replace(/[​‌‍⁠﻿­‭‮]/g, (c) => INVISIBLE[c] ?? "⟨?⟩");
}
