import { FormEvent, useState } from "react";
import { api, errMsg } from "../api";
import { ROLE_LABEL } from "../auth";
import { ErrorBox, Loading, PageHeader, useLoad } from "../components/ui";
import type { Role, User } from "../types";

export default function Users() {
  const users = useLoad(() => api<User[]>("/auth/users"));
  const [form, setForm] = useState({ email: "", display_name: "", role: "recruiter" as Role, password: "" });
  const [error, setError] = useState<string | null>(null);

  async function create(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/auth/users", { body: form });
      setForm({ email: "", display_name: "", role: "recruiter", password: "" });
      users.reload();
    } catch (x) {
      setError(errMsg(x));
    }
  }

  return (
    <>
      <PageHeader title="Users" subtitle="Four roles. No default accounts. Passwords have at least 12 characters." />
      <div className="grid2">
        <div className="card">
          <Loading show={users.loading} />
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
              </tr>
            </thead>
            <tbody>
              {(users.data ?? []).map((u) => (
                <tr key={u.id}>
                  <td>{u.display_name}</td>
                  <td>{u.email}</td>
                  <td>{ROLE_LABEL[u.role]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
              {(Object.keys(ROLE_LABEL) as Role[]).map((r) => (
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
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              required
            />
          </label>
          <ErrorBox error={error || users.error} />
          <button className="btn primary">Create</button>
        </form>
      </div>
    </>
  );
}
