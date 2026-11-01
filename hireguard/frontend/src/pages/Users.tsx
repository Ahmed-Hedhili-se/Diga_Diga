import { ChangeEvent, FormEvent, useState } from "react";
import { api, errMsg } from "../api";
import { ROLE_LABEL, useAuth, usePermission } from "../auth";
import { inboxStatus, laneLabel, permissionLabel } from "../lib/labels";
import { Badge, ConfirmButton, Empty, ErrorBox, fmtDate, Loading, Modal, PageHeader, useLoad } from "../components/ui";
import type { InboxItem, PermissionMatrix, Role, UserAdmin } from "../types";

const ROLES = Object.keys(ROLE_LABEL) as Role[];
const EMPTY_FORM = { email: "", display_name: "", role: "recruiter" as Role, password: "" };

export default function Users() {
  const { user: me } = useAuth();
  const canIngest = usePermission("inbox.ingest");
  const users = useLoad(() => api<UserAdmin[]>("/auth/users"));
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingRole, setPendingRole] = useState<{ u: UserAdmin; role: Role } | null>(null);
  const [tempPassword, setTempPassword] = useState<{ email: string; password: string } | null>(null);

  async function act(fn: () => Promise<unknown>, done: string) {
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(done);
      users.reload();
    } catch (x) {
      setError(errMsg(x));
    }
  }

  const patch = (u: UserAdmin, body: object) =>
    api<UserAdmin>(`/auth/users/${encodeURIComponent(u.id)}`, { method: "PATCH", body });

  async function create(e: FormEvent) {
    e.preventDefault();
    await act(() => api("/auth/users", { body: form }), `Account created for ${form.email}.`);
    setForm(EMPTY_FORM);
  }

  async function resetPassword(u: UserAdmin) {
    setError(null);
    try {
      const r = await api<{ password: string }>(`/auth/users/${encodeURIComponent(u.id)}/reset-password`, { method: "POST" });
      setTempPassword({ email: u.email, password: r.password });
      users.reload();
    } catch (x) {
      setError(errMsg(x));
    }
  }

  return (
    <>
      <PageHeader
        title="Users"
        subtitle="Accounts and roles. Admins manage access but cannot read candidate files or approve HR actions."
      />
      <ErrorBox error={error || users.error} />
      {notice && <div className="alert ok">{notice}</div>}

      <section className="card">
        <h2>Accounts</h2>
        <Loading show={users.loading} />
        {!users.loading && !users.error && !users.data?.length && <Empty>No accounts yet. Create the first one below.</Empty>}
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Status</th>
                <th>Last sign-in</th>
                <th className="num">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(users.data ?? []).map((u) => {
                const self = u.id === me?.id;
                return (
                  <tr key={u.id} className={u.active ? "" : "inactive"}>
                    <td>
                      <div>
                        {u.display_name} {self && <Badge>you</Badge>}
                      </div>
                      <div className="muted small">{u.email}</div>
                    </td>
                    <td>
                      <select
                        aria-label={`Role of ${u.display_name}`}
                        value={u.role}
                        disabled={self || !u.active}
                        onChange={(e) => setPendingRole({ u, role: e.target.value as Role })}
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABEL[r]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <div className="badges">
                        {u.active ? <Badge tone="ok">active</Badge> : <Badge>deactivated</Badge>}
                        {u.locked_until && <Badge tone="warn">locked until {fmtDate(u.locked_until)}</Badge>}
                      </div>
                    </td>
                    <td className="small">{fmtDate(u.last_login_at)}</td>
                    <td className="num">
                      <div className="row end">
                        {u.locked_until && (
                          <button className="btn small" onClick={() => act(() => patch(u, { unlock: true }), `${u.email} unlocked.`)}>
                            Unlock
                          </button>
                        )}
                        <ConfirmButton
                          className="btn small"
                          label="Reset password"
                          title={`Reset the password of ${u.display_name}?`}
                          message={
                            self
                              ? "A temporary password is generated and shown once. All your sessions close, so you will need it to sign in again."
                              : "A temporary password is generated and shown once. All their sessions are closed."
                          }
                          confirmLabel="Reset password"
                          disabled={!u.active}
                          onConfirm={() => resetPassword(u)}
                        />
                        {!self &&
                          (u.active ? (
                            <ConfirmButton
                              className="btn small danger-outline"
                              label="Deactivate"
                              title={`Deactivate ${u.display_name}?`}
                              message="They are signed out everywhere immediately and can no longer sign in. Their history stays in the audit log."
                              confirmLabel="Deactivate"
                              danger
                              onConfirm={() => act(() => patch(u, { active: false }), `${u.email} deactivated.`)}
                            />
                          ) : (
                            <button className="btn small" onClick={() => act(() => patch(u, { active: true }), `${u.email} reactivated.`)}>
                              Reactivate
                            </button>
                          ))}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid2 section-gap">
        <form className="card stack" onSubmit={create}>
          <h2>Add user</h2>
          <label>
            Email
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
          </label>
          <label>
            Display name
            <input value={form.display_name} maxLength={80} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required />
          </label>
          <label>
            Role
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Initial password
            <input
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={256}
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              aria-describedby="pw-rule"
              required
            />
            <span id="pw-rule" className="muted small">
              At least 12 characters. Common passwords and passwords containing the email are refused.
            </span>
          </label>
          <button className="btn primary">Create account</button>
        </form>
        <PermissionTable />
      </div>

      {canIngest && <IngestEml />}

      <Modal
        open={pendingRole !== null}
        title="Change role?"
        onClose={() => setPendingRole(null)}
        actions={
          <>
            <button className="btn ghost" onClick={() => setPendingRole(null)}>
              Cancel
            </button>
            <button
              className="btn primary"
              onClick={async () => {
                const p = pendingRole!;
                setPendingRole(null);
                await act(() => patch(p.u, { role: p.role }), `${p.u.email} is now ${ROLE_LABEL[p.role]}.`);
              }}
            >
              Change role
            </button>
          </>
        }
      >
        {pendingRole && (
          <p>
            <strong>{pendingRole.u.display_name}</strong> goes from {ROLE_LABEL[pendingRole.u.role]} to{" "}
            <strong>{ROLE_LABEL[pendingRole.role]}</strong>. Their sessions are closed so the new permissions apply at
            their next sign-in.
          </p>
        )}
      </Modal>

      <Modal
        open={tempPassword !== null}
        title="Temporary password"
        onClose={() => setTempPassword(null)}
        actions={
          <button className="btn primary" onClick={() => setTempPassword(null)}>
            I have shared it securely
          </button>
        }
      >
        {tempPassword && (
          <>
            <p>
              Give this password to <strong>{tempPassword.email}</strong> through a separate channel. It is shown only
              now and is not stored in readable form.
            </p>
            <code className="secret" tabIndex={0}>
              {tempPassword.password}
            </code>
          </>
        )}
      </Modal>
    </>
  );
}

function PermissionTable() {
  const m = useLoad(() => api<PermissionMatrix>("/auth/permissions"));
  return (
    <section className="card">
      <h2>Permission matrix</h2>
      <p className="muted small">Read-only. The same matrix drives the API guards and this interface.</p>
      <ErrorBox error={m.error} />
      <Loading show={m.loading} rows={6} />
      {m.data && (
        <div className="table-wrap matrix">
          <table className="table">
            <thead>
              <tr>
                <th>Permission</th>
                {ROLES.map((r) => (
                  <th key={r} className="center-cell">
                    {ROLE_LABEL[r]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {m.data.permissions.map((p) => (
                <tr key={p}>
                  <td>
                    <span title={p}>{permissionLabel(p)}</span>
                  </td>
                  {ROLES.map((r) => {
                    const yes = m.data!.roles[r]?.includes(p);
                    return (
                      <td key={r} className={`center-cell ${yes ? "yes" : "no"}`} aria-label={yes ? "allowed" : "denied"}>
                        {yes ? "✓" : "·"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

const MAX_EML = 256 * 1024;

function IngestEml() {
  const [result, setResult] = useState<InboxItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function upload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setError(null);
    setResult(null);
    if (file.size > MAX_EML) return setError("This email is larger than 256 KB.");
    setBusy(true);
    try {
      setResult(await api<InboxItem>("/inbox/ingest", { raw: { data: file, type: "message/rfc822" } }));
    } catch (x) {
      setError(errMsg(x));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card section-gap">
      <h2>Demo data: ingest an email</h2>
      <p className="muted small">
        Loads a fictional <code>.eml</code> into the inbox. It goes through SPF/DKIM/DMARC checks and the email gate
        like real mail. You won't see its content here: reading the inbox is an HR permission.
      </p>
      <label className="btn file-btn">
        {busy ? "Uploading…" : "Choose .eml file"}
        <input type="file" accept=".eml,message/rfc822" onChange={upload} disabled={busy} className="visually-hidden" />
      </label>
      <ErrorBox error={error} />
      {result && (
        <div className="alert ok">
          Ingested as <strong>{result.id}</strong>: lane <strong>{laneLabel(result.lane)}</strong>, status {inboxStatus(result.status)}.
        </div>
      )}
    </section>
  );
}
