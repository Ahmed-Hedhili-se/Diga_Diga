import { ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
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

const ERROR_TITLES: Record<string, string> = {
  "401": "Your session has ended",
  "403": "Permission denied",
  "404": "Not found",
  "409": "Conflict",
  "413": "Too large",
  "422": "Rejected by the server",
  "429": "Too many requests",
};

/** A failed request is never shown as "no data": it says what failed and whether anything was saved. */
export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  const m = /^(\d{3}): ([\s\S]*)$/.exec(error); // errMsg() formats API errors as "<status>: <detail>"
  const code = m?.[1];
  const detail = m ? m[2] : error;
  const offline = !code && /failed to fetch|networkerror|load failed/i.test(error);
  const title = code ? ERROR_TITLES[code] ?? (Number(code) >= 500 ? "Server error" : "Request failed") : offline ? "Cannot reach the server" : null;
  const hint =
    code === "403" ? "The server refused this for your role. Hidden buttons are not the protection; this check is."
    : code === "401" ? "Sign in again to continue."
    : code && Number(code) >= 500 ? "The request failed: this is not an empty result. Try again in a moment."
    : offline ? "Check the connection. Nothing was saved."
    : null;
  return (
    <div className="alert danger" role="alert">
      {title && <strong>{title}{code ? ` (${code})` : ""}: </strong>}
      {offline ? null : detail}
      {hint && <div className="small">{hint}</div>}
    </div>
  );
}

/** Skeleton rows while data loads (announced to screen readers as "Loading"). */
export function Loading({ show, rows = 3 }: { show: boolean; rows?: number }) {
  if (!show) return null;
  return (
    <div className="skeleton" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-bar" style={{ width: `${92 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty muted">{children}</div>;
}

/** Native <dialog>: focus trap, Esc to close and inert background come from the browser. */
export function Modal({ open, title, onClose, children, actions }: {
  open: boolean; title: string; onClose: () => void; children: ReactNode; actions?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} className="modal" aria-labelledby={titleId} onClose={onClose}>
      <h2 id={titleId}>{title}</h2>
      <div className="stack">{children}</div>
      {actions && <div className="row end modal-actions">{actions}</div>}
    </dialog>
  );
}

/** Every action that changes something asks first. */
export function ConfirmButton({ label, title, message, confirmLabel = "Confirm", danger, onConfirm, className = "btn", disabled }: {
  label: ReactNode; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean;
  onConfirm: () => Promise<void> | void; className?: string; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    try {
      await onConfirm();
    } catch {
      /* callers show their own error message */
    } finally {
      setBusy(false);
      setOpen(false);
    }
  }
  return (
    <>
      <button type="button" className={className} disabled={disabled || busy} onClick={() => setOpen(true)}>
        {label}
      </button>
      <Modal
        open={open}
        title={title}
        onClose={() => setOpen(false)}
        actions={
          <>
            <button type="button" className="btn ghost" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </button>
            <button type="button" className={`btn ${danger ? "danger" : "primary"}`} onClick={go} disabled={busy} autoFocus>
              {busy ? "Working…" : confirmLabel}
            </button>
          </>
        }
      >
        {message}
      </Modal>
    </>
  );
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
