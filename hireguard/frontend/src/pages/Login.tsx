import { FormEvent, useEffect, useState } from "react";
import { ApiError, errMsg } from "../api";
import { useAuth } from "../auth";

export default function Login() {
  const { login, notice } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [blockedFor, setBlockedFor] = useState(0); // seconds, after too many failures from this network
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (blockedFor <= 0) return;
    const id = window.setTimeout(() => setBlockedFor(blockedFor - 1), 1000);
    return () => window.clearTimeout(id);
  }, [blockedFor]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setBlockedFor(err.retryAfter ?? 60);
      } else if (err instanceof ApiError && err.status === 401) {
        setError("Invalid email or password.");
      } else {
        setError(errMsg(err));
      }
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  const mins = Math.floor(blockedFor / 60);
  const secs = String(blockedFor % 60).padStart(2, "0");

  return (
    <div className="login-page">
      <form className="card login-card" onSubmit={submit} aria-describedby="login-help">
        <div className="brand big">
          <img src="/favicon.svg" alt="" width={34} height={34} />
          <span>HireGuard</span>
        </div>
        <p className="tagline">Smart enough to help, secure enough to trust.</p>
        {notice && (
          <div className="alert info" role="status">
            {notice}
          </div>
        )}
        <label>
          Email
          <input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <div className="alert danger" role="alert">
            {error}
          </div>
        )}
        {blockedFor > 0 && (
          <div className="alert warn" role="alert">
            Too many failed sign-ins from this network. Try again in {mins}:{secs}.
          </div>
        )}
        <button className="btn primary" disabled={busy || blockedFor > 0}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p id="login-help" className="muted small">
          For your security, sign-in to an account is paused for 15 minutes after 5 failed attempts. No default
          accounts exist: your administrator gives you your access.
        </p>
      </form>
    </div>
  );
}
